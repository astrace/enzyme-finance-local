import pytest
import time

from brownie import (
    Dispatcher, GasRelayPaymasterLib, #BeaconProxyFactory,
    GasRelayPaymasterFactory, FundDeployer, ValueInterpreter,
    ExternalPositionFactory, PolicyManager, FeeManager,
    IntegrationManager, PolicyManager, ComptrollerLib,
    ProtocolFeeReserveLib, ExternalPositionManager,
    ProtocolFeeTracker, VaultLib, ProtocolFeeTracker,
    UniswapV3Adapter,
    accounts, Wei
)
from collections import namedtuple
from eth_abi import encode_abi

ONE_DAY_IN_SECONDS = 86_400

USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
MLN = "0xec67005c4e498ec7f55e092bd1d35cbc47c91892"
ZERO = "0x0000000000000000000000000000000000000000"

# GSN
RELAY_HUB = "0x9e59Ea5333cD4f402dAc320a04fafA023fe3810D"
TRUSTED_FORWARDER = "0xAa3E82b4c4093b4bA13Cb5714382C99ADBf750cA"

UNISWAP_V2_ROUTER_02 = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"

DEPLOYMENT_ACCOUNT = accounts.load('deployment_account')

Vault = namedtuple("Vault", ["creator", "vaultProxy", "comptrollerProxy"])

def _deploy(contract, *args):
    return contract.deploy(*args, {'from': DEPLOYMENT_ACCOUNT})

@pytest.fixture(scope="module")
def enzyme_core_contracts():
    dispatcher = _deploy(Dispatcher)
    gas_relay_paymaster_lib =_deploy(GasRelayPaymasterLib, WETH, RELAY_HUB, TRUSTED_FORWARDER)
    gas_relay_paymaster_factory = _deploy(GasRelayPaymasterFactory, dispatcher, gas_relay_paymaster_lib)
    
    fund_deployer = _deploy(FundDeployer, dispatcher, gas_relay_paymaster_factory)
    # set current fund deployer
    dispatcher.setCurrentFundDeployer(fund_deployer, {'from': DEPLOYMENT_ACCOUNT})

    protocol_fee_reserve_lib = _deploy(ProtocolFeeReserveLib)
    external_position_factory = _deploy(ExternalPositionFactory, dispatcher)
    
    policy_manager = _deploy(PolicyManager, fund_deployer, gas_relay_paymaster_factory)
    external_position_manager = _deploy(ExternalPositionManager, fund_deployer, external_position_factory, policy_manager)

    value_interpreter = _deploy(ValueInterpreter, fund_deployer, WETH, ONE_DAY_IN_SECONDS)
    # add primitive to allow USDT
    # NOTE: If you are going to use any denominationa asset other than WETH,
    #       you must call this function and add the appropriate aggregator !!!
    value_interpreter.addPrimitives([USDT], ["0x3E7d1eAB13ad0104d2750B8863b489D65364e32D"], [1])

    integration_manager =  _deploy(IntegrationManager, fund_deployer, policy_manager, value_interpreter)

    uniswap_v3_adapter = _deploy(UniswapV3Adapter, integration_manager.address, UNISWAP_V3_ROUTER)

    protocol_fee_reserve = _deploy(ProtocolFeeReserveLib)
    fee_manager = _deploy(FeeManager, fund_deployer)

    comptroller_lib = _deploy(
        ComptrollerLib,
        dispatcher, protocol_fee_reserve, fund_deployer,
        value_interpreter, external_position_manager, fee_manager,
        integration_manager, policy_manager, gas_relay_paymaster_factory,
        MLN, WETH
    )
    # set comptroller lib
    fund_deployer.setComptrollerLib(comptroller_lib, {'from': DEPLOYMENT_ACCOUNT})

    protocol_fee_tracker = _deploy(ProtocolFeeTracker, fund_deployer)
    # set protocol fee tracker
    fund_deployer.setProtocolFeeTracker(protocol_fee_tracker, {'from': DEPLOYMENT_ACCOUNT})
    
    vault_lib = _deploy(
        VaultLib,
        external_position_manager, gas_relay_paymaster_factory,
        protocol_fee_reserve, protocol_fee_tracker,
        MLN, ZERO, WETH, 1_000_000,
    )
    # set vault lib
    fund_deployer.setVaultLib(vault_lib, {'from': DEPLOYMENT_ACCOUNT})
    # set release live
    fund_deployer.setReleaseLive({'from': DEPLOYMENT_ACCOUNT})

    return {
        "fund_deployer": fund_deployer,
        "integration_manager": integration_manager,
        "uniswap_v3_adapter": uniswap_v3_adapter
    }

@pytest.fixture
def new_fund(enzyme_core_contracts):
    fund_deployer = enzyme_core_contracts["fund_deployer"]
    tx = fund_deployer.createNewFund(
        accounts[0], "MyFund", "XYZ", USDT, 0, b'', b'',
        {"from": accounts[0]}
    )
    assert "NewFundCreated" in tx.events
    event = tx.events["NewFundCreated"]
    vault = Vault(event["creator"], event["vaultProxy"], event["comptrollerProxy"]) 
    return vault

def _buy_USDT(Contract, web3, chain, account, eth_value):

    usdt_contract = Contract.from_explorer(USDT)
    
    # check allowance
    if usdt_contract.allowance(account, UNISWAP_V2_ROUTER_02) == 0:
        # infinite approve
        usdt_contract.approve(
            UNISWAP_V2_ROUTER_02, 2**256 - 1,
            {'from': account}
        )
    
    # params
    amountOutMin = 0
    path = [WETH, USDT]
    to = account
    deadline = chain.time() + ONE_DAY_IN_SECONDS
    value = Wei("1 ether")

    uniswap_v2_contract = Contract.from_explorer(UNISWAP_V2_ROUTER_02)
    tx2 = uniswap_v2_contract.swapExactETHForTokens(
        amountOutMin, path, to, deadline,
        {'from': account, 'value': value}
    )
    assert Contract.from_explorer(USDT).balanceOf(account) > 0

def _get_comptroller(web3, fund):
    abi = open("./abis/comptroller_lib.abi").read().strip()
    comptroller_proxy_contract = web3.eth.contract(
        address=fund.comptrollerProxy,
        abi=abi
    )
    return comptroller_proxy_contract

def _buy_shares(Contract, web3, chain, fund, buyer, amount):

    _buy_USDT(Contract, web3, chain, buyer, Wei("100 ether"))
    
    abi = open("./abis/comptroller_lib.abi").read().strip()
    comptroller_proxy_contract = web3.eth.contract(
        address=fund.comptrollerProxy,
        abi=abi
    )
    # approve before buying
    usdt_contract = Contract.from_explorer(USDT)
    usdt_contract.approve(
        fund.comptrollerProxy, amount,
        {'from': buyer}
    )
    assert usdt_contract.allowance(buyer, fund.comptrollerProxy) == amount
    
    # buy shares
    comptroller_proxy_contract.functions.buyShares(amount, 1).transact({'from': buyer})

    # check balance
    abi = open("./abis/vault_lib.abi").read().strip()
    vault_proxy_contract = web3.eth.contract(
        address=fund.vaultProxy,
        abi=abi
    )
    return vault_proxy_contract.functions.balanceOf(buyer).call()

def test_buy_shares(Contract, web3, chain, new_fund):
    buyer = web3.eth.accounts[0]
    amount = 1_000 * 1_000_000
    ret =_buy_shares(Contract, web3, chain, new_fund, buyer, amount)
    assert ret == amount * 10 ** 12

def test_make_trade(Contract, web3, chain, enzyme_core_contracts, new_fund):
    # first, deposit some money into fund via buying shares
    buyer = web3.eth.accounts[0]
    amount = 1_000 * 1_000_000
    ret =_buy_shares(Contract, web3, chain, new_fund, buyer, amount)
    
    ### set up input to trade function

    # integrationData
    pathAddresses = [USDT, WETH]
    pathFees = [500]
    outgoingAssetAmount = 500_000_000 # 500 USDT
    minIncomingAssetAmount = 0

    integrationData = encode_abi(
        ['address[]', 'uint24[]', 'uint256', 'uint256'],
        [pathAddresses, pathFees, outgoingAssetAmount, minIncomingAssetAmount]
    )

    # UniswapV3Adapter
    adapter = enzyme_core_contracts["uniswap_v3_adapter"]
    selector = bytes.fromhex("03e38a2b")

    callArgs = encode_abi(
        ['address', 'bytes4', 'bytes'],
        [adapter.address, selector, integrationData]
    )

    integration_manager = enzyme_core_contracts["integration_manager"]
    action_id = 0

    comptroller = _get_comptroller(web3, new_fund)

    comptroller.functions.callOnExtension(
        integration_manager.address, action_id, callArgs
    ).transact({"from": buyer})

    # check that the vault has both USDT and WETH
    vault_addr = new_fund.vaultProxy
    usdt_bal = Contract.from_explorer(USDT).balanceOf(vault_addr) 
    weth_bal = Contract.from_explorer(WETH).balanceOf(vault_addr) 

    assert usdt_bal > 0 and weth_bal > 0

