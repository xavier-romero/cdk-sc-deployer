# Deploying on Sepolia setting Docker compose

Example execution for deploying a network on Sepolia and running it with docker compose:

### 1. Name your network and create an output folder
    NETWORK_NAME=my_network
    mkdir $NETWORK_NAME

### 2. Set required L1 params
Set these 2 params required by deployment to working values:

    L1_RPC_URL=https://sepolia_endpoint_supporting_preEIP155_txs
    L1_FUNDED_PRIVATE_KEY=<private_key_for_account_with_funds_on_Sepolia>

By default, 5ETH are used from the funded wallet to fund each of these accounts:
- Deployer (which will be the Admin as well)
- Sequencer
- Aggregator


### 3. Run the deployment
#### 3.1. For Rollup
    docker run --name deployer --rm \
        -v $(pwd)/$NETWORK_NAME:/output \
        -e L1_RPC_URL=$L1_RPC_URL \
        -e L1_FUNDED_PRIVATE_KEY=$L1_FUNDED_PRIVATE_KEY \
        -e IS_VALIDUM=0 \
        -e COMPOSE_CONFIG=1 \
        -e NETWORK_NAME=$NETWORK_NAME \
        hermeznetwork/cdk-sc-deployer

#### 3.2. For Validium
    docker run --name deployer --rm \
        -v $(pwd)/$NETWORK_NAME:/output \
        -e L1_RPC_URL=$L1_RPC_URL \
        -e L1_FUNDED_PRIVATE_KEY=$L1_FUNDED_PRIVATE_KEY \
        -e IS_VALIDUM=1 \
        -e DAC_URLS=http://${NETWORK_NAME}-dac:8484 \
        -e COMPOSE_CONFIG=1 \
        -e NETWORK_NAME=$NETWORK_NAME \
        hermeznetwork/cdk-sc-deployer

Be sure that gas price is not much higher than 150gweis, otherwise you can easily hit tx fee capping from many providers, breaking the deployment and having to start from scratch.

### 4. Optional - Adjust versions
Versions to be used are set on file ```.env``` on the network folder. It's meant to be a working combination, but depending on your context -like setting another forkid, etc.- you may want to change them.

    cd $NETWORK_NAME
    cat .env


### 5. Bring everything up
From that same network folder:

    docker compose up -d
