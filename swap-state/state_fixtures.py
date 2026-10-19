"""Synthetic raw layouts, never funded or sent. No keys or signing material."""
import base64
import copy
import hashlib
from state import (PROGRAM,TOKEN,NATIVE,SYSTEM,AUTHORITY,LOADER,GENESIS,POOL_FIELDS,decode,b58,account_keys)
from swap_fixtures import fixture as packet_fixture, edit_wire, fake_key, NOW


def encoded(raw,owner,lamports=2039280,executable=False):
    return {'owner':owner,'executable':executable,'lamports':lamports,
            'data':[base64.b64encode(raw).decode(),'base64']}


def put64(raw,offset,value):
    raw[offset:offset+8] = value.to_bytes(8,'little')


def raw_mint(decimals=6, *, freeze=None):
    raw=bytearray(82); put64(raw,36,10000000); raw[44:46]=bytes([decimals,1])
    if freeze:
        raw[46:50]=(1).to_bytes(4,'little'); raw[50:82]=decode(freeze)
    return encoded(raw,TOKEN)


def raw_token(mint,owner,amount=10000,native=False):
    raw=bytearray(165); raw[:32]=decode(mint); raw[32:64]=decode(owner); put64(raw,64,amount); raw[108]=1
    if native:
        raw[109:113]=(1).to_bytes(4,'little'); put64(raw,113,2039280)
    return encoded(raw,TOKEN,2039280+amount if native else 2039280)


def received(value):
    return {'state':'received','result':value}


def fixture(*, with_packet=False, native=False, reverse=False):
    packet=packet_fixture(); a=packet['policy']['accounts']; a['authority']=AUTHORITY
    edit_wire(packet,lambda m:m['accountKeys'].__setitem__(m['accountKeys'].index(fake_key('authority')),AUTHORITY))
    mint0, mint1 = a['inputMint'],a['outputMint']
    if native: mint0=NATIVE
    p={'config':a['config'],'creator':fake_key('creator'),'vault0':a['inputVault'],'vault1':a['outputVault'],
       'lpMint':fake_key('lp-mint'),'mint0':mint0,'mint1':mint1,'program0':TOKEN,'program1':TOKEN,'observation':a['observation']}
    if reverse:
        for prefix in ('vault','mint'):
            p[prefix+'0'],p[prefix+'1']=p[prefix+'1'],p[prefix+'0']
    raw=bytearray(637); raw[:8]=hashlib.sha256(b'account:PoolState').digest()[:8]
    for i,name in enumerate(POOL_FIELDS): raw[8+32*i:40+32*i]=decode(p[name])
    decimals=[9 if p['mint'+str(i)]==NATIVE else 6 for i in (0,1)]
    raw[328:333]=bytes([255,0,9,*decimals]); put64(raw,373,NOW//1000-100)
    pool=encoded(raw,PROGRAM)
    config=bytearray(236); config[:8]=hashlib.sha256(b'account:AmmConfig').digest()[:8]
    put64(config,12,2500); put64(config,20,120000); put64(config,28,40000)
    observation=bytearray(4075); observation[:8]=hashlib.sha256(b'account:ObservationState').digest()[:8]
    observation[8]=1; observation[11:43]=decode(a['pool'])
    program=(2).to_bytes(4,'little')+decode(fake_key('programdata'))
    rows=[pool,encoded(config,PROGRAM),raw_mint(decimals[0]),raw_mint(decimals[1]),
          raw_token(p['mint0'],AUTHORITY,native=p['mint0']==NATIVE),
          raw_token(p['mint1'],AUTHORITY,native=p['mint1']==NATIVE),encoded(observation,PROGRAM),encoded(program,LOADER,executable=True)]
    for i in (0,1):
        if p['mint'+str(i)]==NATIVE:
            mint_data=bytearray(base64.b64decode(rows[2+i]['data'][0]));put64(mint_data,36,0)
            rows[2+i]['data'][0]=base64.b64encode(mint_data).decode()
    if with_packet:
        rows += [encoded(b'',SYSTEM,100000),raw_token(a['inputMint'],a['wallet'],1000),raw_token(a['outputMint'],a['wallet'],0)]
    ev={'genesisBefore':received(GENESIS['devnet']),'genesisAfter':received(GENESIS['devnet']),
        'bootstrap':received({'context':{'slot':100},'value':[copy.deepcopy(pool)]}),
        'accounts':received({'context':{'slot':101},'value':rows}),
        'blockTime':received(NOW//1000),'blockhash':received({'context':{'slot':101},'value':True}),
        'fee':received({'context':{'slot':102},'value':5001}),
        'discovery':{'state':'not-requested'},'transaction':{'state':'not-requested'}}
    from contract import validate
    return {'format':'cpmm-state-capture-1','network':'devnet','origin':'synthetic-offline',
            'selection':'prior-packet' if with_packet else 'explicit-pool','pool':a['pool'],
            'packet':packet if with_packet else None,'startedAtMs':NOW-500,'finishedAtMs':NOW,
            'accountKeys':account_keys(a['pool'],p,packet if with_packet else None),'blockTimeSlot':101,
            'messageSha256':validate(packet,now_ms=NOW)['wireMessageSha256'],
            'evidence':ev,'requests':[],'rpcRequestsAttempted':0,'transactionsSent':0,'ledgerUpdated':False}


def change_row(capture,index,offset,data,bootstrap=False):
    row=capture['evidence']['bootstrap' if bootstrap else 'accounts']['result']['value'][index]
    raw=bytearray(base64.b64decode(row['data'][0])); raw[offset:offset+len(data)]=data
    row['data'][0]=base64.b64encode(raw).decode()
    return capture
