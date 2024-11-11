# CDK SC Deployer
This repo aims to provide a docker image that takes care of deploying CDK Smart Contracts and generate the exact output required to deploy the CDK stack.

## Supported modes
Deploying SC and generating config files for the following scenarios:
- CDK Validium ForkId 9
- CDK Rollup ForkId 9
- CDK Validium ForkId 11
- CDK Rollup ForkId 11
- CDK Validium ForkId 12
- CDK Rollup ForkId 12
- CDK Validium ForkId 13
- CDK Rollup ForkId 13

## Usage
The intended usage is through a Docker image generated from this repo.

Example with minimal parameters:
```bash
# Create output folder where all files will be saved
mkdir output
# Run the deployer
docker run --name "cdk-sc-deployer" --rm --network=host \
    -v $(pwd)/output:/output \
    -e L1_RPC_URL=http://127.0.0.1:34369 \
    -e L1_FUNDED_MNEMONIC="code code code code code code code code code code code quality" \
    hermeznetwork/cdk-sc-deployer:latest
```

Notes:
*The param ```--network=host``` is only required in case of a local L1 endpoint (127.0.0.1).*
*However, this flag does not work for MAC users, so if that's your case you will need [a workaround](https://medium.com/@lailadahi/getting-around-dockers-host-network-limitation-on-mac-9e4e6bfee44b).*

### Docker Image
There is a docker image available at ```hermeznetwork/cdk-sc-deployer```, but you can build it yourself locally if you want: ```docker build -t cdk-sc-deployer .```

### Available input ENV vars
| Env Var | Description | Required | Default value
| ------- | ----------- | -------- | ------------- |
| L1_RPC_URL | Full URL for the L1 endpoint to use. | Yes | - |
| L1_FUNDED_MNEMONIC | Mnemonic for the account with funds on L1.<br>This takes precedence over ```L1_FUNDED_PRIVATE_KEY```, but one of both has to be set. | Yes* | - |
| L1_FUNDED_PRIVATE_KEY | Private key for the account with funds on L1.<br>```L1_FUNDED_MNEMONIC``` takes precedence over this, but one of both has to be set. | Yes* | - |
| MODE | Operation mode. Can be one of:<br> - full: Full deployment<br> - offline: Generating config from existing network | No | full |
| NETWORK_NAME | Name of the network, used for SC deployment and for Erigon configuration. | No | kurtosis |
| L2_CHAIN_ID | ChainId for the L2 network to deploy. | No | 10101 |
| FORKID | Forkid to deploy. | No | 11 |
| IS_VALIDIUM | 0 for rollup, 1 for validium. | No | 0 |
| DAC_URLS | String with comma-separated URLs for DAC nodes.<br>Only used if ```IS_VALIDIUM=1```.| No | - |
| REAL_VERIFIER | 0 if we will use mockprover, 1 for real prover. | No | 0 |
| DEPLOY_GAS_TOKEN | 1 if we want to deploy and use gas token. | No | 0 |
| GAS_TOKEN_ADDRESS | Address for an existing Gas Token to use.<br>If an address is specified, ```DEPLOY_GAS_TOKEN``` will be automatically disabled. | No | - |
| TRUSTED_SEQUENCER_URL | URL for the trusted Sequencer RPC.<br>If omitted you should manually update SC later with the right URL. | No | http://sequencer |
| L1_FUND_AMOUNT | ETH Amount to send to Sequencer & Aggregator on L1. | No | 5 |
| ADDRESSES | Pre-defined addresses to be used for sequencer, aggregator, etc.<br>If omitted, random accounts will be generated. | No | - |
| COMPOSE_CONFIG | If set, configuration files are pre-set for Docker Compose.<br>That means mainly that URLs are set matching services names from ```compose.yaml```. | No | 1 |
| JSON_EXTRA_PARAMS | Extra parameters to be used when rendering templates. | No | - |
| ERIGON_GASLESS | Allow free transactions. | No | 0 |
| OVERWRITE_OUTPUT | Remove content of output's folder instead exiting. | No | 0 |

#### ADDRESSES
You can specify just one, many or all of them. You can also take the content of a previous ```wallets.json``` as example.

Example usage:
```bash
docker run --name "cdk-sc-deployer" --rm --network=host \
    -v $(pwd)/output:/output \
    -e L1_RPC_URL=http://127.0.0.1:34369 \
    -e L1_FUNDED_MNEMONIC="code code code code code code code code code code code quality" \
    -e ADDRESSES='{ 
        "aggregator":{"private_key":"0x0000000000000000000000000000000000000000000000000000000000000001"},
        "sequencer":{"private_key":"0x0000000000000000000000000000000000000000000000000000000000000002"}
    }' \
    hermeznetwork/cdk-sc-deployer:latest

```

#### JSON_EXTRA_PARAMS
The params set here will be used to render templates, check Templates section for reference.
The syntax is the same than for ADDRESSES, just json content, example:



## Output
The following files will be copied on the output folder:
- ```wallets.json```: Details(address, private key, mnemonic, keystore password) for all accounts.
- SC Deployment files:
    - input:
        - ```create_rollup_parameters.json```
        - ```deploy_parameters.json```
    - from deployment/v2:
        - ```deploy_output.json```
        - ```genesis.json```
        - ```create_rollup_output.json```
    - from .openzeppelin:
        - ```network-<network_name>.json```
- Keystore files:
    - ```sequencer.keystore```
    - ```aggregator.keystore```
    - ```claimtxmanager.keystore```
    - ```dac.keystore``` (if Validium mode)
- Stack configuration files (*):
    - ```aggregator-config.toml```: For zkevm-aggregator
    - ```dac-config.toml```: For cdk-data-availability
    - ```dynamic-kurtosis-allocs.json```: For cdk-erigon
    - ```dynamic-kurtosis-chainspec.json```: For cdk-erigon
    - ```dynamic-kurtosis-conf.json```: For cdk-erigon
    - ```erigon-rpc.yaml```: For cdk-erigon RPC
    - ```erigon-sequencer.yaml```: For cdk-erigon sequencer
    - ```executor-config.json```: For zkProver executor
    - ```mockprover-config.json```: For zkProver prover (mock mode)
    - ```node-genesis.json```: For zkevm-aggregator and zkevm-sequence-sender
    - ```ssender-config.toml```: For zkevm-sequence-sender
    - ```pool-manager-config.toml```: For zkevm-pool-manager
    - ```bridge-config.toml```: For zkevm-bridge-service


## Config Templates
Output configuration files are rendered from templates on the [/templates](./templates) folder from the docker image.
So, if you're not happy with default templates, you can provide yours by mapping your own templates folder, by adding something like this to the ```docker run``` command
```bash
-v /your/full/path/to/templates:/templates
```
All instances in the template following this format:
```
{{.variable_name}}
```
Will be replaced with the corresponding value.
### Built-in template variables
These variables are already defined and can be used in your templates:
| variable | value |
| -------- | ----- |
| {{.l1_rpc_url}} | L1 RPC endpoint |
| {{.l1_chain_id}} | L1 Chain Id discovered from the L1 endpoint |
| {{.l2_chain_id}} | L2 Chain Id |
| {{.rollup_fork_id}} | ForkID |
| {{.network_name}} | Network name |
| {{.admin.address}} | Address for the Admin account |
| {{.sequencer_keystore_password}} | Keystore password for the Sequencer |
| {{.aggregator.address}} | Address for the Aggregator |
| {{.aggregator_keystore_password}} | Keystore password for the Aggregator |
| {{.sequencer.address}} | Address for the Sequencer |
| {{.aggregator.address}} | Address for the Aggregator |
| {{.claimtxmanager_keystore_password}} | Keystore password for the Claim TX Manager |
| {{.polAddress}} | POL Address from deploy_output.json, field polTokenAddress |
| {{.zkevmAddress}} | Address from create_rollup_output.json, rollupAddress field |
| {{.rollupAddress}} | Address from deploy_output.json, field polygonRollupManagerAddress | 
| {{.gerAddress}} | Address from deploy_output.json, field polygonZkEVMGlobalExitRootAddress | 
| {{.ger_l2_address}} | Address from the genesis for PolygonZkEVMGlobalExitRootL2 Proxy | 
| {{.polygonDataCommitteeAddress}} | Address for the Data committee from create_rollup_output.json, field polygonDataCommitteeAddress | 
| {{.bridgeAddress}} | Addres for the Bridge |
| {{.rollupBlockNumber}} | Block number from create_rollup_output.json, field createRollupBlockNumber | 
| {{.rollupManagerBlockNumber}} | Address from deploy_output.json, field deploymentRollupManagerBlockNumber | 
| {{.is_validium}} | Lowercase bool -go format-: true of false |
| {{.gasless}} | Lowercase bool -go format-: true of false |

#### Custom variables
Arbitrary variables for template rendering can be provided through JSON_EXTRA_PARAMS, for example:
```
-e JSON_EXTRA_PARAMS='{
    "dac_port":8484,
    "executor_port":50071,
    "l1_ws_url":"ws://el-1-geth-lighthouse:8546",
    "rpc_ds":"rpc001:6900",
    "rpc_rpc":"http://rpc001:8123",
    "sequencer_ds":"sequencer001:6900",
    "sequencer_ds_port":6900,
    "sequencer_rpc":"http://sequencer001:8123",
    "sequencer_rpc_port":8123,
    "stateless_executor":"executor001"
    }' \
```
So, you could fill your templates with variables like:
```
{{.dac_port}}
{{.executor_port}}
...
```

## Examples
See some specific examples on [docs folder](/docs).