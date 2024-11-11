# Contracts
Each folder is an instance of repo https://github.com/0xPolygonHermez/zkevm-contracts on the right branch for the named forkid.

Then you need to edit hardhat.config.ts, and replace that first line
```
import "dotenv/config";
```

With:
```
   import { config as dotEnvConfig } from "dotenv";
   dotEnvConfig();
```

Modifiy Dockerfile by adding same steps done for existing forkids.
You can remove some folder to reduce the size as much as possible:
```
.git*
artifacts
node_modules
typechain-types
```