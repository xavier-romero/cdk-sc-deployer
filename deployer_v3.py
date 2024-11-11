import os
import json
import datetime
import sys
import secrets
import fileinput
import subprocess
import shutil
from eth_account import Account
from eth_abi import encode
from eth_keyfile import create_keyfile_json
from web3 import Web3, exceptions as web3_exceptions
from glob import glob


# Dynamic configuration passed as env var
INPUT = {
    'start': bool(int(os.getenv('START', 1))),
    'mode': os.getenv('MODE', 'full'),  # full, offline, add
    'etherscan_apikey': os.getenv('ETHERSCAN_API_KEY'),
    'forkid': int(os.getenv('FORKID', 11)),
    # bool('0') == True, bool(0) == False
    'real_verifier': bool(int(os.getenv('REAL_VERIFIER', 0))),
    'network_name': os.getenv('NETWORK_NAME', 'kurtosis'),
    'l2_chain_id': int(os.getenv('L2_CHAIN_ID', 10101)),
    'is_validium': bool(int(os.getenv('IS_VALIDIUM', 0))),
    'dac_urls': os.getenv('DAC_URLS'),  # used if validium
    'l1_rpc_url': os.getenv('L1_RPC_URL'),
    'l1_fund_amount': float(os.getenv('L1_FUND_AMOUNT', 5)),
    'l1_funded_private_key': os.getenv('L1_FUNDED_PRIVATE_KEY', None),
    'l1_funded_mnemonic': os.getenv('L1_FUNDED_MNEMONIC'),
    'deploy_gas_token': bool(int(os.getenv('DEPLOY_GAS_TOKEN', 0))),
    'gas_token_address': os.getenv('GAS_TOKEN_ADDRESS'),
    'addresses': os.getenv('ADDRESSES', '{}'),
    'extra_params': os.getenv('JSON_EXTRA_PARAMS', '{}'),
    'overwrite_output': bool(int(os.getenv('OVERWRITE_OUTPUT', '0'))),
    'trusted_sequencer_url': os.getenv(
        'TRUSTED_SEQUENCER_URL', 'http://sequencer'),
    'compose_config': bool(int(os.getenv('COMPOSE_CONFIG', 1))),
    'erigon_gasless': bool(int(os.getenv('ERIGON_GASLESS', 0))),
}

# Static configuration
CONFIG = {
    "output": "/output",
    "input": "/input",
    "input_files": {
        'offline': [
            "genesis.json",
            "create_rollup_output.json",
            "deploy_output.json",
            "create_rollup_parameters.json",
            "deploy_parameters.json",
            "wallets.json",
        ],
        'add': [
            "genesis.json",
            "deploy_output.json",
        ]
    },
    "contracts": "./contracts",
    "config_templates": "./templates",
    "templates_condition": {
        "compose.yaml": INPUT.get('compose_config'),
        "dac-config.toml": INPUT.get('is_validium'),
        "compose-dac.yaml":
            INPUT.get('is_validium') and INPUT.get('compose_config')
    },
    "deployment_helpers_path": "deployment/helpers/deployment-helpers.ts",
    "gas_token": {
        "compiled_source": "artifacts/contracts/mocks/ERC20PermitMock.sol/ERC20PermitMock.json",  # noqa
        "constructor_arg_types": ['string', 'string', 'address', 'uint256'],
        "constructor_arg_values": [
            "CDK Gas Tolen", "CDK", "0x0", 1000000000000000000000000],
        "gas": 1312708,
        "address": None,
    },
    "deploy_output_files_source": [
        "deployment/v2/deploy_output.json",
        "deployment/v2/genesis.json",
        "deployment/v2/create_rollup_output.json",
        ".openzeppelin/*.json"
    ],
    "deploy_output_files_destination": "deployment",
    "config_files_destination": {
        "compose.yaml": "/",
        "compose-dac.yaml": "/",
        ".env": "/",
        "*": "/config"
    },
    "keystore_files_destination": "config/keystores",
    "node_genesis": "node-genesis.json",
    "wallets_json": "wallets.json",
}

# Generic global variables
WALLETS = {}  # filled on create_wallets()
ADDRESSES = json.loads(INPUT.get('addresses'))
L1_W = None
OUTPUT_FILES = {}  # noqa filled on save_deployment_files(), or process_input_files() if offline
now = datetime.datetime.now()
OUTPUT_LOG_FILENAME = \
    f"{CONFIG['output']}/cdk_sc_deployer_{now.hour:02}" \
    f"{now.minute:02}{now.second:02}.log"
OUTPUT_LOG = os.open(OUTPUT_LOG_FILENAME, os.O_RDWR | os.O_CREAT)
OUTPUT_FOLDER = CONFIG.get('output')
REPLACE_MAP = {
    # Common
    'l1_chain_id': ('INPUT', 'l1_chain_id'),  # filled after L1_W is created
    'sequencer.address': ('WALLETS', 'sequencer', 'addr'),
    'l1_rpc_url': ('INPUT', 'l1_rpc_url'),
    # ERigon:
    'l2_chain_id': ('INPUT', 'l2_chain_id'),
    'network_name': ('INPUT', 'network_name'),
    'polAddress': ('OUTPUT_FILES', 'deploy_output.json', 'polTokenAddress'),
    'admin.address': ('WALLETS', 'admin', 'addr'),
    'zkevmAddress': ('OUTPUT_FILES', 'create_rollup_output.json', 'rollupAddress'),  # noqa
    'rollupAddress': ('OUTPUT_FILES', 'deploy_output.json', 'polygonRollupManagerAddress'),  # noqa
    'gerAddress': ('OUTPUT_FILES', 'deploy_output.json', 'polygonZkEVMGlobalExitRootAddress'),  # noqa
    'rollupBlockNumber': ('OUTPUT_FILES', 'create_rollup_output.json', 'createRollupBlockNumber'),  # noqa
    'rollupManagerBlockNumber': ('OUTPUT_FILES', 'deploy_output.json', 'deploymentRollupManagerBlockNumber'),  # noqa
    'gasless': ('DIRECT', str(INPUT.get('erigon_gasless')).lower()),
    # Aggregator:
    'aggregator.address': ('WALLETS', 'aggregator', 'addr'),
    'rollup_fork_id': ('INPUT', 'forkid'),
    'ger_l2_address': ('GENESIS', 'PolygonZkEVMGlobalExitRootL2 proxy'),
    'aggregator_keystore_password': ('WALLETS', 'aggregator', 'keystore_password'),  # noqa
    'is_validium': ('DIRECT', str(INPUT.get('is_validium')).lower()),
    # SSender
    'sequencer_keystore_password': ('WALLETS', 'sequencer', 'keystore_password'),  # noqa
    # DAC
    'polygonDataCommitteeAddress': ('OUTPUT_FILES', 'create_rollup_output.json', 'polygonDataCommitteeAddress'),  # noqa
    # Bridge
    'bridgeAddress': ('OUTPUT_FILES', 'deploy_output.json', 'polygonZkEVMBridgeAddress'),  # noqa
    'claimtxmanager_keystore_password': ('WALLETS', 'claimtxmanager', 'keystore_password'),  # noqa
}
if INPUT.get('forkid') == 9:
    REPLACE_MAP['contracts_version'] = ('DIRECT', 'elderberry')
elif INPUT.get('forkid') == 11:
    REPLACE_MAP['contracts_version'] = ('DIRECT', 'elderberry')
elif INPUT.get('forkid') == 12:
    REPLACE_MAP['contracts_version'] = ('DIRECT', 'banana')
elif INPUT.get('forkid') == 13:
    REPLACE_MAP['contracts_version'] = ('DIRECT', 'banana')

compose_config = INPUT.get('compose_config')
is_validium = INPUT.get('is_validium')
if is_validium:
    REPLACE_MAP['polygonDataCommitteeAddress'] = \
        ('OUTPUT_FILES', 'create_rollup_output.json', 'polygonDataCommitteeAddress')  # noqa
    REPLACE_MAP['dac_keystore_password'] = \
        ('WALLETS', 'dac', 'keystore_password')
OFFLINE_MODE = INPUT.get('mode') == 'offline'
ADD_NETWORK_MODE = INPUT.get('mode') == 'add'
FULL_MODE = INPUT.get('mode') == 'full'


def _say(message):
    now = datetime.datetime.now()
    msg = \
        f"[{now.year}-{now.month:02}-{now.day:02} " \
        f"{now.hour:02}:{now.minute:02}:{now.second:02}] {message}"
    print(msg)
    msg += '\n'
    os.write(OUTPUT_LOG, msg.encode())
    os.fsync(OUTPUT_LOG)


def _get_contracts_folder():
    base_path = CONFIG.get('contracts')
    forkid = INPUT.get('forkid')

    if forkid == 9:
        return f"{base_path}/forkid9"
    elif forkid == 11:
        return f"{base_path}/forkid11"
    elif forkid == 12:
        return f"{base_path}/forkid12"
    elif forkid == 13:
        return f"{base_path}/forkid13"
    else:
        raise ValueError(f"Invalid forkid: {forkid}")


def _l1_tx(
    src_prvkey, dst_addr=None, eth_amount=0, data=None, wait=False, gas=21000,
    get_receipt=False
):
    src_addr = Web3().eth.account.from_key(str(src_prvkey)).address
    src_addr = Web3.to_checksum_address(src_addr)
    if dst_addr:
        dst_addr = Web3.to_checksum_address(dst_addr)
    src_balance = L1_W.eth.get_balance(src_addr)

    gas_price = int(L1_W.eth.gas_price * 1.10)
    wei_amount = Web3().to_wei(eth_amount, 'ether')

    try:
        assert (src_balance >= (wei_amount + gas*gas_price))
    except AssertionError:
        _say(
            "*** ERROR. Not enough balance on source account:"
            f"{Web3().from_wei(src_balance, 'ether')} | "
            f"desired:{Web3().from_wei(wei_amount + gas*gas_price, 'ether')}"
        )
        sys.exit(1)

    tx = {
        'chainId': L1_W.eth.chain_id,
        'nonce': L1_W.eth.get_transaction_count(src_addr, 'pending'),
        'value': wei_amount,
        'gas': gas,
        'gasPrice': gas_price,
    }
    if dst_addr:
        tx['to'] = dst_addr
    if data:
        tx['data'] = data

    # sign the transaction
    signed_tx = L1_W.eth.account.sign_transaction(tx, src_prvkey)

    # send transaction
    tx_hash = L1_W.eth.send_raw_transaction(signed_tx.raw_transaction).hex()
    _say(
        f"Sending tx:{tx_hash} from:{src_addr} to:{dst_addr} "
        f"amount:{eth_amount} gas:{gas} gasPrice:{gas_price}"
    )
    if wait or get_receipt:
        try:
            receipt = L1_W.eth.wait_for_transaction_receipt(
                tx_hash, timeout=300, poll_latency=2
            )
        except web3_exceptions.TimeExhausted:
            _say(f"*** ERROR: could not confirm tx with txhash: {tx_hash}")
            sys.exit(1)
        if get_receipt:
            return receipt

    return tx_hash


def process_input_files():
    if not (OFFLINE_MODE or ADD_NETWORK_MODE):
        _say("ERROR: process_input_files called in full mode")
        sys.exit(1)

    input_dir = CONFIG.get('input')
    for _file in CONFIG.get('input_files').get(INPUT.get('mode')):
        shutil.copy(
            f"{input_dir}/{_file}",
            f"{OUTPUT_FOLDER}/{CONFIG['deploy_output_files_destination']}/"
        )
        with open(f"{input_dir}/{_file}") as f:
            _say(f"Reading input file {_file}")
            OUTPUT_FILES[_file] = json.load(f)

    if OFFLINE_MODE:
        INPUT['network_name'] = \
            OUTPUT_FILES['create_rollup_parameters.json']['networkName']
        _say(f"Set network name to {INPUT['network_name']}")
        INPUT['l2_chain_id'] = \
            OUTPUT_FILES['create_rollup_parameters.json']['chainID']
        _say(f"Set L2 chain id to {INPUT['l2_chain_id']}")
    elif ADD_NETWORK_MODE:
        # Setting files on contract folder to attach to existing rollup!
        contracts_folder = _get_contracts_folder()
        for _file in CONFIG.get('input_files').get(INPUT.get('mode')):
            shutil.copy(
                f"{input_dir}/{_file}",
                f"{contracts_folder}/deployment/v2/{_file}"
            )
            _say(f"Copying {_file} to {contracts_folder}/deployment/v2")


def check_env():
    global L1_W

    input_dir = CONFIG.get('input')
    overwrite_output = INPUT.get('overwrite_output')
    if overwrite_output:
        for filename in os.listdir(OUTPUT_FOLDER):
            # Avoid removing the log file we just created
            if OUTPUT_LOG_FILENAME.endswith(filename):
                continue
            file_path = os.path.join(OUTPUT_FOLDER, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                _say('Failed to delete %s. Reason: %s' % (file_path, e))
                sys.exit(1)

    if not overwrite_output and len(os.listdir(OUTPUT_FOLDER)) > 1:
        _say(f"Output directory {OUTPUT_FOLDER} is not empty, exiting")
        sys.exit(0)

    os.mkdir(f"{OUTPUT_FOLDER}/{CONFIG['deploy_output_files_destination']}")
    for cfg_output_dir in CONFIG['config_files_destination'].values():
        _full_path = f"{OUTPUT_FOLDER}/{cfg_output_dir}"
        if os.path.isdir(_full_path):
            continue
        else:
            os.mkdir(_full_path)
    # os.mkdir(f"{output_dir}/{CONFIG['config_files_destination']}")
    os.mkdir(f"{OUTPUT_FOLDER}/{CONFIG['keystore_files_destination']}")

    if OFFLINE_MODE or ADD_NETWORK_MODE:
        try:
            _ = os.listdir(input_dir)
        except FileNotFoundError:
            _say("ERROR: Input folder not found, exiting")
            sys.exit(1)
        else:
            process_input_files()
            if OFFLINE_MODE:
                return

    if not INPUT.get('l1_rpc_url'):
        raise ValueError("Missing L1_RPC_URL env var")

    if INPUT.get('l1_funded_mnemonic'):
        Web3().eth.account.enable_unaudited_hdwallet_features()
        INPUT['l1_funded_private_key'] = \
            '0x' + \
            Web3().eth.account.from_mnemonic(
                INPUT.get('l1_funded_mnemonic')
            ).key.hex()
    elif not INPUT.get('l1_funded_private_key'):
        raise ValueError(
            "No L1_FUNDED_MNEMONIC or L1_FUNDED_PRIVATE_KEY provided")

    if is_validium and not INPUT.get('dac_urls'):
        raise ValueError("Missing DAC_URLS to setup committee")

    L1_W = Web3(Web3.HTTPProvider(INPUT.get('l1_rpc_url')))
    INPUT['l1_chain_id'] = L1_W.eth.chain_id


def process_extra_params():
    extra_params = json.loads(INPUT.get('extra_params'))
    for k, v in extra_params.items():
        if not isinstance(v, dict):
            _say(f"Adding extra param: {k}={v}")
            REPLACE_MAP[k] = ('DIRECT', v)
        else:
            for k2, v2 in v.items():
                _say(f"Adding extra param: {k}.{k2}={v2}")
                REPLACE_MAP[f"{k}.{k2}"] = ('DIRECT', v2)


def dump_input():
    _say("Input parameters:")
    for k, v in INPUT.items():
        _say(f"{k}={v}")


def docker_compose_setup():
    nname = INPUT.get('network_name')
    compose_replacements = {
        'rpc_rpc': ('DIRECT', f"http://{nname}-rpc:8123"),
        'rpc_ds': ('DIRECT', f"{nname}-rpc:6900"),
        'sequencer_rpc': ('DIRECT', f"http://{nname}-sequencer:8123"),
        'sequencer_ds': ('DIRECT', f"{nname}-sequencer:6900"),
        'stateless_executor': ('DIRECT', f"{nname}-executor"),
        'pm_url': ('DIRECT', f"http://{nname}-poolmanager:8545"),
        'executor_port': ('DIRECT', '50071'),
        'aggregator_host': ('DIRECT', f"{nname}-aggregator"),
        'aggregator_port': ('DIRECT', '50081'),
        'sequencer_ds_port': ('DIRECT', '6900'),
        'sequencer_rpc_port': ('DIRECT', '8123'),
        'pm_port': ('DIRECT', '8545'),
        'dac_port': ('DIRECT', '8484'),
        'bridge_port': ('DIRECT', '8080'),
        'bridge_db.user': ('DIRECT', 'bridge_user'),
        'bridge_db.password': ('DIRECT', 'bridge_password'),
        'bridge_db.name': ('DIRECT', 'bridge_db'),
        'bridge_db.hostname': ('DIRECT', f"{nname}-db"),
        'bridge_db.port': ('DIRECT', '5432'),
        'aggr_db.user': ('DIRECT', 'aggregator_user'),
        'aggr_db.password': ('DIRECT', 'aggregator_password'),
        'aggr_db.name': ('DIRECT', 'aggregator_db'),
        'aggr_db.hostname': ('DIRECT', f"{nname}-db"),
        'aggr_db.port': ('DIRECT', '5432'),
        'aggrsync_db.user': ('DIRECT', 'sync_user'),
        'aggrsync_db.password': ('DIRECT', 'sync_password'),
        'aggrsync_db.name': ('DIRECT', 'sync_db'),
        'aggrsync_db.hostname': ('DIRECT', f"{nname}-db"),
        'aggrsync_db.port': ('DIRECT', '5432'),
        'pm_db.user': ('DIRECT', 'pm_user'),
        'pm_db.password': ('DIRECT', 'pm_password'),
        'pm_db.name': ('DIRECT', 'pm_db'),
        'pm_db.hostname': ('DIRECT', f"{nname}-db"),
        'pm_db.port': ('DIRECT', '5432'),
        'dac_db.user': ('DIRECT', 'dac_user'),
        'dac_db.password': ('DIRECT', 'dac_password'),
        'dac_db.name': ('DIRECT', 'dac_db'),
        'dac_db.hostname': ('DIRECT', f"{nname}-db"),
        'dac_db.port': ('DIRECT', '5432'),
    }
    for k, v in compose_replacements.items():
        _say(f"Adding param (COMPOSE_CONFIG): {k}={v[1]}")
        REPLACE_MAP[k] = v

    original_umask = os.umask(0o000)
    try:
        for v in [
            'postgres', 'erigon-sequencer-datadir', 'erigon-rpc-datadir',
            'seqsender',
        ]:
            _say(f"Creating folder {OUTPUT_FOLDER}/data/{v}")
            os.makedirs(f"{OUTPUT_FOLDER}/data/{v}", mode=0o777)
    finally:
        os.umask(original_umask)


def create_wallets():
    global WALLETS
    wallets_json = f"{CONFIG.get('output')}/{CONFIG.get('wallets_json')}"

    WALLETS = {
        "admin": {},
        "sequencer": {"keystore_password": secrets.token_urlsafe(16)},
        "claimtxmanager": {"keystore_password": secrets.token_urlsafe(16)},
        "aggregator": {"keystore_password": secrets.token_urlsafe(16)},
        "agglayer": {},
        "proofsigner": {}
    }
    if is_validium:
        WALLETS["dac"] = {"keystore_password": secrets.token_urlsafe(16)}

    if OFFLINE_MODE:
        for k in WALLETS.keys():
            WALLETS[k] |= OUTPUT_FILES['wallets.json'].get(k, {})
        # For legacy wallets.json
        WALLETS['sequencer'] |= OUTPUT_FILES['wallets.json'].get('Sequencer', {})  # noqa
        WALLETS['admin'] |= OUTPUT_FILES['wallets.json'].get('Deployment', {})
        WALLETS['claimtxmanager'] |= OUTPUT_FILES['wallets.json'].get('ClaimTX', {})  # noqa
        WALLETS['aggregator'] |= OUTPUT_FILES['wallets.json'].get('Aggregator', {})  # noqa
        return

    for addr in WALLETS.keys():
        if not WALLETS[addr].get('prvkey'):
            Account.enable_unaudited_hdwallet_features()
            (acct, WALLETS[addr]['mnemonic']) = Account.create_with_mnemonic()
            WALLETS[addr]['addr'] = acct.address
            WALLETS[addr]['prvkey'] = acct.key.hex()

    addrs_to_parse = [
        'admin', 'sequencer', 'aggregator', 'claimtxmanager', 'agglayer',
        'proofsigner'
    ]
    if is_validium:
        addrs_to_parse.append('dac')
    for addr in addrs_to_parse:
        if _k := ADDRESSES.get(addr, {}).get('mnemonic'):
            _act = Web3().eth.account.from_mnemonic(_k)
            WALLETS[addr]['addr'] = _act.address
            WALLETS[addr]['prvkey'] = _act.key.hex()
            WALLETS[addr]['mnemonic'] = _k
        elif _k := ADDRESSES.get(addr, {}).get('private_key'):
            _act = Web3().eth.account.from_key(_k)
            WALLETS[addr]['addr'] = _act.address
            WALLETS[addr]['prvkey'] = _k
            if WALLETS[addr].get('mnemonic'):
                del WALLETS[addr]['mnemonic']

    _say(f"Wallets created:\n{json.dumps(WALLETS, indent=4)}")

    f = open(wallets_json, "w")
    json.dump(WALLETS, f, indent=2)
    f.close()


def create_keystores():
    keystore_path = \
        f"{CONFIG.get('output')}/{CONFIG.get('keystore_files_destination')}"
    for k, v in WALLETS.items():
        kp = v.get('keystore_password')
        if kp:
            pk = v.get('prvkey')
            ks = \
                create_keyfile_json(
                    int(pk, 16).to_bytes(32),
                    bytes(kp, 'utf-8')
                )
            ks_file = f"{keystore_path}/{k.lower()}.keystore"
            with open(ks_file, "w") as f:
                json.dump(ks, f, indent=2)
            _say(f"Created keystore file {ks_file}")


def fund_accounts():
    if OFFLINE_MODE:
        _say("Skipping account funding in offline mode")
        return

    L1_FUND_AMOUNT = INPUT.get('l1_fund_amount')
    L1_FUNDED_PRIVATE_KEY = INPUT.get('l1_funded_private_key')

    addresses_to_fund = [
        ('admin', WALLETS.get('admin').get('addr'), False),
        ('sequencer', WALLETS.get('sequencer').get('addr'), False),
        ('aggregator', WALLETS.get('aggregator').get('addr'), True),
    ]

    for (_, _addr, _confirm) in addresses_to_fund:
        transfer_kwargs = {
            'src_prvkey': L1_FUNDED_PRIVATE_KEY,
            'eth_amount': L1_FUND_AMOUNT,
        }
        _l1_tx(**transfer_kwargs, dst_addr=_addr, wait=_confirm)

    for (_name, _addr, _) in addresses_to_fund:
        eth_balance = \
            float(Web3().from_wei(L1_W.eth.get_balance(_addr), 'ether'))
        assert (eth_balance >= L1_FUND_AMOUNT)

        _say(f"Confirmed balance for {_name}({_addr}): {eth_balance}ETH")


def deploy_gas_token():
    if OFFLINE_MODE:
        _say("Skipping gas token deployment in offline mode")
        return

    gas_token_addr = INPUT.get('gas_token_address')
    if gas_token_addr:
        CONFIG['gas_token']['address'] = gas_token_addr
        _say(f"Using existing gas token address: {gas_token_addr}")
        return

    admin_addr = WALLETS.get('admin').get('addr')
    constructor_types = CONFIG.get('gas_token').get('constructor_arg_types')
    constructor_values = [
        admin_addr if x == "0x0" else x
        for x in CONFIG.get('gas_token').get('constructor_arg_values')
    ]
    artifact_file = _get_contracts_folder() + "/" + \
        CONFIG.get('gas_token').get('compiled_source')
    with open(artifact_file, 'r') as f:
        artifact = json.load(f)
        bytecode = artifact.get('bytecode')

    args = encode(constructor_types, constructor_values)
    bytecode += args.hex()

    receipt = _l1_tx(
        src_prvkey=INPUT.get('l1_funded_private_key'),
        data=bytecode,
        gas=CONFIG.get('gas_token').get('gas'),
        get_receipt=True
    )
    gas_token_addr = receipt['contractAddress']
    CONFIG['gas_token']['address'] = gas_token_addr

    _say(f"Deployed gas token, address: {gas_token_addr}")


def create_hh_env_file():
    if OFFLINE_MODE:
        _say("Skipping env file creation in offline mode")
        return

    admin_mnemonic = WALLETS.get('admin').get('mnemonic')
    etherscan_apikey = INPUT.get('etherscan_apikey')
    l1_rpc_url = INPUT.get('l1_rpc_url')
    output_folder = _get_contracts_folder()

    env_file = open(f"{output_folder}/.env", "w")
    # It does not need to be sepolia, it can be any rpc url
    env_file.write(f'SEPOLIA_PROVIDER={l1_rpc_url}\n')
    env_file.write(f'MNEMONIC={admin_mnemonic}\n')
    if etherscan_apikey:
        env_file.write(f'ETHERSCAN_API_KEY="{etherscan_apikey}"\n')
    env_file.close()

    _say(f"Created env file in {output_folder}")


def create_parameter_files():
    if OFFLINE_MODE:
        _say("Skipping parameter files creation in offline mode")
        return

    output_folder = f"{OUTPUT_FOLDER}/" \
        f"{CONFIG.get('deploy_output_files_destination')}"
    contracts_folder = _get_contracts_folder()

    real_verifier = INPUT.get('real_verifier')
    network_name = INPUT.get('network_name')
    l2_chainid = INPUT.get('l2_chain_id')
    forkid = INPUT.get('forkid')

    sequencer_addr = WALLETS.get('sequencer').get('addr')
    admin_addr = WALLETS.get('admin').get('addr')
    aggregator_addr = WALLETS.get('aggregator').get('addr')

    # CREATE ROLLUP PARAMS
    create_rollup_parameters = {
        "realVerifier": real_verifier,
        "trustedSequencerURL": INPUT.get('trusted_sequencer_url'),
        "networkName": f"{network_name}",
        "description": "0.0.1",
        "trustedSequencer": f"{sequencer_addr}",
        "chainID": l2_chainid,
        "adminZkEVM": f"{admin_addr}",
        "forkID": forkid,
        "consensusContract": "PolygonZkEVMEtrog",
        "gasTokenAddress": CONFIG.get('gas_token').get('address') or "",
        "deployerPvtKey": "",
        "maxFeePerGas": "",
        "maxPriorityFeePerGas": "",
        "multiplierGas": "",
    }
    if is_validium:
        create_rollup_parameters["consensusContract"] = "PolygonValidiumEtrog"
        create_rollup_parameters["dataAvailabilityProtocol"] = \
            "PolygonDataCommittee"

    create_rollup_files = [
        f"{output_folder}/create_rollup_parameters.json",
        f"{contracts_folder}/deployment/v2/create_rollup_parameters.json",
    ]

    for file in create_rollup_files:
        f = open(file, "w")
        json.dump(create_rollup_parameters, f, indent=2)
        f.close()
    _say(
        "Create rollup parameters:\n"
        f"{json.dumps(create_rollup_parameters, indent=4)}")

    # DEPLOYMENT PARAMS
    if FULL_MODE:
        deployment_parameters = {
            "test": True,
            "timelockAdminAddress": f"{admin_addr}",
            "minDelayTimelock": 3600,
            "salt": f"0x{secrets.token_hex(32)}",
            "initialZkEVMDeployerOwner": f"{admin_addr}",
            "admin": f"{admin_addr}",
            "trustedAggregator": f"{aggregator_addr}",
            "trustedAggregatorTimeout": 604799,
            "pendingStateTimeout": 604799,
            "emergencyCouncilAddress": f"{admin_addr}",
            "polTokenAddress": "",
            "zkEVMDeployerAddress": "",
            "deployerPvtKey": "",
            "maxFeePerGas": "",
            "maxPriorityFeePerGas": "",
            "multiplierGas": ""
        }

        deploy_parameters_files = [
            f"{output_folder}/deploy_parameters.json",
            f"{contracts_folder}/deployment/v2/deploy_parameters.json",
        ]

        for file in deploy_parameters_files:
            f = open(file, "w")
            json.dump(deployment_parameters, f, indent=2)
            f.close()
        _say(
            "Deployment parameters:\n"
            f"{json.dumps(deployment_parameters, indent=4)}")


def deployment_helper_set_gas_price():
    if OFFLINE_MODE:
        _say("Skipping gas price setting in offline mode")
        return

    contracts_folder = _get_contracts_folder()
    DEPLOYMENT_HELPER = \
        contracts_folder + '/' + CONFIG.get('deployment_helpers_path')

    gas_price_gwei = Web3().from_wei(L1_W.eth.gas_price, 'gwei')
    gas_price_gwei = round(float(gas_price_gwei)*1.10, 8)

    for line in fileinput.input(DEPLOYMENT_HELPER, inplace=1):
        if "const gasPriceKeylessDeployment" in line:
            line = \
                f"const gasPriceKeylessDeployment = '{gas_price_gwei:.8f}';\n"
        sys.stdout.write(line)
    _say(
        f"Patched file {DEPLOYMENT_HELPER} to gasPrice "
        f"{gas_price_gwei:.8f} gweis"
    )


def deploy_contracts():
    if OFFLINE_MODE:
        _say("Skipping contract deployment in offline mode")
        return

    full_steps = [
        "npx hardhat run deployment/testnet/prepareTestnet.ts --network sepolia",  # noqa
        "npx ts-node deployment/v2/1_createGenesis.ts",
        "npx hardhat run deployment/v2/2_deployPolygonZKEVMDeployer.ts --network sepolia",  # noqa
        "npx hardhat run deployment/v2/3_deployContracts.ts --network sepolia",
    ]
    rollup_steps = [
        "npx hardhat run deployment/v2/4_createRollup.ts --network sepolia",
    ]
    if FULL_MODE:
        steps = full_steps + rollup_steps
    elif ADD_NETWORK_MODE:
        steps = rollup_steps

    for step in steps:
        _say(f"Running: {step}")
        subprocess.check_call(step, shell=True, cwd=_get_contracts_folder())

    # IF verificable:
    # npx hardhat run deployment/v2/verifyContracts.js --network sepolia


def save_deployment_files():
    if OFFLINE_MODE:
        _say("Skipping deployment files saving in offline mode")
        return

    dst_folder = \
        f"{CONFIG['output']}/" \
        f"{CONFIG['deploy_output_files_destination']}"
    contracts_folder = _get_contracts_folder()

    files_to_save = []
    for file in CONFIG['deploy_output_files_source']:
        if '*' in file:
            if _f := glob(rf"{contracts_folder}/{file}"):
                files_to_save.extend(_f)
        else:
            files_to_save.append(f"{contracts_folder}/{file}")

    for file in files_to_save:
        _say(f"Copying {file} to {dst_folder}")
        if ".openzeppelin/unknown" in file:
            dst = f"{dst_folder}/network-{INPUT.get('network_name')}.json"
            shutil.copy(file, dst)
        else:
            shutil.copy(file, dst_folder)
        with open(file) as f:
            OUTPUT_FILES[os.path.basename(file)] = json.load(f)


def update_wallets():
    if OFFLINE_MODE:
        _say("Skipping wallet update in offline mode")
        return

    global WALLETS

    deploy_output_folder = \
        f"{OUTPUT_FOLDER}/{CONFIG.get('deploy_output_files_destination')}"
    wallets_json = f"{OUTPUT_FOLDER}/{CONFIG.get('wallets_json')}"

    f1 = open(f"{deploy_output_folder}/deploy_output.json")
    data1 = json.load(f1)
    f1.close()

    f2 = open(f"{deploy_output_folder}/create_rollup_output.json")
    data2 = json.load(f2)
    f2.close()

    WALLETS['pol'] = {'addr': data1['polTokenAddress']}
    WALLETS['rollup'] = {'addr': data2['rollupAddress']}

    f = open(wallets_json, "w")
    json.dump(WALLETS, f, indent=2)
    f.close()


def approve_pol():
    if OFFLINE_MODE:
        _say("Skipping POL approval in offline mode")
        return

    spender_addr = WALLETS.get('rollup').get('addr')
    sequencer_addr = WALLETS.get('sequencer').get('addr')
    sequencer_prvkey = WALLETS.get('sequencer').get('prvkey')
    pol_addr = WALLETS.get('pol').get('addr')

    token = L1_W.eth.contract(
        address=pol_addr,
        abi=[
            {
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "approve",
                "outputs": [
                    {
                        "name": "success",
                        "type": "bool"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            },
        ]
    )

    max_amount = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff  # noqa

    tx = token.functions.approve(spender_addr, max_amount).build_transaction({
        'from': sequencer_addr,
        'nonce': 0
    })

    signed_tx = L1_W.eth.account.sign_transaction(tx, sequencer_prvkey)
    tx_hash = L1_W.eth.send_raw_transaction(signed_tx.raw_transaction)
    _say(f"Approved {max_amount} to {spender_addr} on tx {tx_hash.hex()}")


def setup_dac():
    if OFFLINE_MODE:
        _say("Skipping DAC setup in offline mode")
        return

    admin_addr = WALLETS.get('admin').get('addr')
    admin_prvkey = WALLETS.get('admin').get('prvkey')
    admin_nonce = L1_W.eth.get_transaction_count(admin_addr)
    dac_c_addr = OUTPUT_FILES.get('create_rollup_output.json') \
        .get('polygonDataCommitteeAddress')
    dac_addr = WALLETS.get('dac').get('addr')
    rollup_addr = OUTPUT_FILES.get('create_rollup_output.json') \
        .get('rollupAddress')

    dac_urls = INPUT.get('dac_urls').split(',')
    dac_count = len(dac_urls)

    dac_c = L1_W.eth.contract(
        address=dac_c_addr,
        abi=[
            {
                "inputs": [
                    {"name": "_requiredAmountOfSignatures", "type": "uint256"},
                    {"name": "urls", "type": "string[]"},
                    {"name": "addrsBytes", "type": "bytes"},
                ],
                "name": "setupCommittee",
                "outputs": [],
                "stateMutability": "view",
                "type": "function"
            },
        ]
    )

    tx = dac_c.functions.setupCommittee(dac_count, dac_urls, dac_addr) \
        .build_transaction({'from': admin_addr, 'nonce': admin_nonce})

    signed_tx = L1_W.eth.account.sign_transaction(tx, admin_prvkey)
    tx_hash = L1_W.eth.send_raw_transaction(signed_tx.raw_transaction)
    _say(
        f"Executed setupCommittee({dac_count}, {dac_urls}, {dac_addr}) "
        f"on tx {tx_hash.hex()}"
    )

    rollup = L1_W.eth.contract(
        address=rollup_addr,
        abi=[
            {
                "inputs": [
                    {"name": "newDataAvailabilityProtocol", "type": "address"},
                ],
                "name": "setDataAvailabilityProtocol",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
        ]
    )

    tx = rollup.functions.setDataAvailabilityProtocol(dac_c_addr) \
        .build_transaction({'from': admin_addr, 'nonce': admin_nonce + 1})

    signed_tx = L1_W.eth.account.sign_transaction(tx, admin_prvkey)
    tx_hash = L1_W.eth.send_raw_transaction(signed_tx.raw_transaction)
    _say(
        f"Executed setDataAvailabilityProtocol({dac_c_addr}) "
        f"on tx {tx_hash.hex()}"
    )


def create_erigon_network_files():
    output_folder = \
        f"{OUTPUT_FOLDER}/" \
        f"{CONFIG.get('config_files_destination').get('*')}"
    genesis = OUTPUT_FILES['genesis.json']
    rollup_output = OUTPUT_FILES['create_rollup_output.json']

    network_name = INPUT.get('network_name')

    erigon_dyn_allocs = {
        x.get('address'): {
            'contractName': x.get('contractName'),
            'balance': x.get('balance'),
            'nonce': x.get('nonce'),
            'code': x.get('bytecode'),
            'storage': x.get('storage')
        }
        for x in genesis.get('genesis')
    }

    erigon_dyn_conf = {
        'root': genesis.get('root'),
        'timestamp': rollup_output['firstBatchData']['timestamp'],
        'gasLimit': 0,
        'difficulty': 0
    }

    erigon_dyn_chainspec = {
        "ChainName": f"dynamic-{network_name}",
        "chainId": INPUT.get('l2_chain_id'),
        "consensus": "ethash",
        "homesteadBlock": 0,
        "daoForkBlock": 0,
        "eip150Block": 0,
        "eip155Block": 0,
        "byzantiumBlock": 0,
        "constantinopleBlock": 0,
        "petersburgBlock": 0,
        "istanbulBlock": 0,
        "muirGlacierBlock": 0,
        "berlinBlock": 0,
        "londonBlock": 9999999999999999999999999999999999999999999999999,
        "arrowGlacierBlock": 9999999999999999999999999999999999999999999999999,
        "grayGlacierBlock": 9999999999999999999999999999999999999999999999999,
        "terminalTotalDifficulty": 58750000000000000000000,
        "terminalTotalDifficultyPassed": False,
        "shanghaiTime": 9999999999999999999999999999999999999999999999999,
        "cancunTime": 9999999999999999999999999999999999999999999999999,
        "pragueTime": 9999999999999999999999999999999999999999999999999,
        "ethash": {}
    }

    file_chainspec = f"{output_folder}/dynamic-{network_name}-chainspec.json"
    _say(f"Creating file {file_chainspec}")
    with open(file_chainspec, "w") as f:
        json.dump(erigon_dyn_chainspec, f, indent=2)
    # with open(f"{output_folder}/{network_name}-chainspec.json", "w") as f:
    #     json.dump(erigon_dyn_chainspec, f, indent=2)

    file_allocs = f"{output_folder}/dynamic-{network_name}-allocs.json"
    _say(f"Creating file {file_allocs}")
    with open(file_allocs, "w") as f:
        json.dump(erigon_dyn_allocs, f, indent=2)

    file_conf = f"{output_folder}/dynamic-{network_name}-conf.json"
    _say(f"Creating file {file_conf}")
    with open(file_conf, "w") as f:
        json.dump(erigon_dyn_conf, f, indent=2)


def create_config_files():
    replacement = {}
    for k, v in REPLACE_MAP.items():
        if v[0] == 'WALLETS':
            value = WALLETS.get(v[1]).get(v[2])
        elif v[0] == 'OUTPUT_FILES':
            value = OUTPUT_FILES.get(v[1]).get(v[2])
        elif v[0] == 'INPUT':
            value = INPUT.get(v[1])
        elif v[0] == 'GENESIS':
            value = next(
                e['address']
                for e in OUTPUT_FILES.get('genesis.json').get('genesis')
                if e.get('contractName') == v[1]
            )
        elif v[0] == 'DIRECT':
            value = v[1]
        else:
            raise ValueError(f"Invalid value for {k}: {v}")
        replacement[k] = value

    tmpl_path = CONFIG.get('config_templates')

    gasless = INPUT.get('erigon_gasless')

    for filename in os.listdir(tmpl_path):
        if not CONFIG.get('templates_condition').get(filename, True):
            continue
        def_config_folder = CONFIG.get('config_files_destination').get('*')
        config_folder = \
            CONFIG.get('config_files_destination') \
            .get(filename, def_config_folder)
        output_folder = f"{OUTPUT_FOLDER}/{config_folder}"

        with open(f"{tmpl_path}/{filename}", 'r') as f_in:
            _say(f"Creating file {output_folder}/{filename}")
            with open(f"{output_folder}/{filename}", "wt") as f_out:
                for line in f_in:
                    for k, v in replacement.items():
                        line = line.replace("{{."+k+"}}", str(v))
                    if (
                        gasless and ("erigon" in filename) and
                        ("gas-price" in line) and line.startswith('zkevm.')
                    ):
                        continue
                    else:
                        f_out.write(line)

    # Kinda hardcoded here, but we need to append the dac config to compose
    if is_validium and compose_config:
        with open(f"{OUTPUT_FOLDER}/compose.yaml", 'a') as compose:
            compose.write("\n\n")
            with open(f"{OUTPUT_FOLDER}/compose-dac.yaml", 'r') as f_in:
                compose.write(f_in.read())
        os.remove(f"{OUTPUT_FOLDER}/compose-dac.yaml")


def create_node_genesis_file():
    node_genesis_file = \
        f"{CONFIG.get('output')}/" \
        f"{CONFIG.get('config_files_destination').get('*')}" \
        f"/{CONFIG.get('node_genesis')}"
    _say(f"Creating file {node_genesis_file}")

    genesis = OUTPUT_FILES['genesis.json']
    deploy_output = OUTPUT_FILES['deploy_output.json']
    rollup_output = OUTPUT_FILES['create_rollup_output.json']

    l1_config = {
        'polygonZkEVMAddress': rollup_output['rollupAddress'],
        'polTokenAddress': deploy_output['polTokenAddress'],
        'polygonZkEVMGlobalExitRootAddress':
            deploy_output['polygonZkEVMGlobalExitRootAddress'],
        'polygonRollupManagerAddress':
            deploy_output['polygonRollupManagerAddress'],
        'chainId': INPUT.get('l1_chain_id')
    }

    node_genesis = {
        "l1Config": l1_config,
        "l2chainId": INPUT.get('l2_chain_id'),
        "genesisBlockNumber": rollup_output["createRollupBlockNumber"],
        "root": genesis["root"],
        "genesis": genesis["genesis"]
    }

    f = open(node_genesis_file, "w")
    json.dump(node_genesis, f, indent=2)


if not INPUT.get('start'):
    from threading import Event
    _say("Deployment delayed, needs to be manually triggered")
    Event().wait()
    sys.exit(1)

# Set up extra params if provided
process_extra_params()

# Dump input vars to output
dump_input()

# Check that we received required params, exit otherwise
check_env()

# Create addresses and save file wallets.json
create_wallets()

# Steps needed to output everything for docker compose
if compose_config:
    docker_compose_setup()

# Create keystores for the wallets
create_keystores()

# Fund deployer, sequencer and aggregator accounts on L1
fund_accounts()

# Deploy gas token, or use the existing one if provided
if INPUT.get('deploy_gas_token') or INPUT.get('gas_token_address'):
    deploy_gas_token()

# Create env file for hardhat (etherscan api key, nmemonic for deployer)
create_hh_env_file()

# Create deployment parameters files (create_rollup and deploy_parameters)
create_parameter_files()

# Set gas price in deployment helper file to the current value * 1.10
deployment_helper_set_gas_price()

# Do the actual SC deployment
deploy_contracts()

# Save files from SC deployment to output path
save_deployment_files()

# Update wallets.json with new addresses (rollup + pol)
update_wallets()

# Approve POL token spending for sequencer
approve_pol()

# Setup DAC Committee
if is_validium:
    setup_dac()

# Create erigon spec for network
create_erigon_network_files()

# Create various config files
create_config_files()

# Create node genesis file (for ssender, aggregator, etc)
create_node_genesis_file()

sys.exit(0)
