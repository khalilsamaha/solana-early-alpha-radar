import {startPumpPortal} from './pumpportal.js';
import {connectSharedDiscovery} from './pumpportal-shared.js';

// Select once. Shared failure never activates the direct adapter's reconnect loop.
export function startPumpPortalSource(config,onToken,onStatus,health,onCreation) {
  if(config.pumpPortalSource==='shared')
    return connectSharedDiscovery(config.pumpPortalSocket,onToken,onStatus,health,onCreation);
  if(config.pumpPortalSource!=='direct'||config.pumpPortalSocket)
    throw Error('Invalid PumpPortal source');
  return startPumpPortal(config.pumpPortalApiKey,onToken,onStatus,health,onCreation);
}
