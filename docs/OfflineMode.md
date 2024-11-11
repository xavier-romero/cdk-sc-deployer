# Offline mode

This mode allows to generate configuration files for an existing network, so this does not interact with L1 at all.
This requires the relevant files from the existing network:
- ```genesis.json```   
- ```create_rollup_output.json```
- ```deploy_output.json```
- ```create_rollup_parameters.json```
- ```deploy_parameters.json```
- ```wallets.json```

With these files in the ```./input``` folder, you can call the deployer like this:

    mkdir output
    docker run --name deployer --rm \
        -v $(pwd)/output:/output \
        -v $(pwd)/input:/input \
        -e IS_VALIDUM=0 \
        -e COMPOSE_CONFIG=1 \
        hermeznetwork/cdk-sc-deployer

You will get all the related output files on the ```./output``` folder. Nothing will be deployed on L1, note that you don't even need to provide an L1 endpoint/key.