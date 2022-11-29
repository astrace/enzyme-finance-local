import pytest
import time

from brownie import (
    Dispatcher, GasRelayPaymasterLib, #BeaconProxyFactory,
    GasRelayPaymasterFactory, FundDeployer, ValueInterpreter,
    ExternalPositionFactory, PolicyManager, FeeManager,
    IntegrationManager, PolicyManager, ComptrollerLib,
    ProtocolFeeReserveLib, ExternalPositionManager,
    ProtocolFeeTracker, VaultLib, ProtocolFeeTracker,
    accounts, Wei
)
from collections import namedtuple
from eth_abi import encode

ONE_DAY_IN_SECONDS = 86_400

USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
MLN = "0xec67005c4e498ec7f55e092bd1d35cbc47c91892"
ZERO = "0x0000000000000000000000000000000000000000"

# GSN
RELAY_HUB = "0x9e59Ea5333cD4f402dAc320a04fafA023fe3810D"
TRUSTED_FORWARDER = "0xAa3E82b4c4093b4bA13Cb5714382C99ADBf750cA"

UNISWAP_V2_ROUTER_02 = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

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
    integration_manager =  _deploy(IntegrationManager, fund_deployer, policy_manager, value_interpreter)

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
        "fund_deployer": fund_deployer
    }

@pytest.fixture
def new_fund(enzyme_core_contracts):
    fund_deployer = enzyme_core_contracts["fund_deployer"]
    tx = fund_deployer.createNewFund(
        accounts[0], "MyFund", "XYZ", WETH, 0, b'', b'',
        {"from": accounts[0]}
    )
    assert "NewFundCreated" in tx.events
    event = tx.events["NewFundCreated"]
    vault = Vault(event["creator"], event["vaultProxy"], event["comptrollerProxy"]) 
    return vault

def _buy_USDT(Contract, web3, chain, account):

    # approve 1MM USD
    usdt_contract = Contract.from_explorer(USDT)
    tx1 = usdt_contract.approve(
        UNISWAP_V2_ROUTER_02, 1_000_000 * 1_000_000,
        {'from': account}
    )
    # params
    amountOutMin = 0
    path = [WETH, USDT]
    to = account.address
    deadline = chain.time() + ONE_DAY_IN_SECONDS
    value = Wei("1 ether")

    uniswap_v2_contract = Contract.from_explorer(UNISWAP_V2_ROUTER_02)
    tx2 = uniswap_v2_contract.swapExactETHForTokens(
        amountOutMin, path, to, deadline,
        {'from': account, 'value': value}
    )
    assert Contract.from_explorer(USDT).balanceOf(account.address) > 0


def test_buy_shares(Contract, web3, chain, new_fund):
    _buy_USDT(Contract, web3, chain, accounts[0])
    
    abi = open("./abis/comptroller_lib.abi").read().strip()
    comptroller_proxy_contract = web3.eth.contract(
        address=new_fund.comptrollerProxy,
        abi=abi
    )
    #buyShares(uint256 _investmentAmount, uint256 _minSharesQuantity)

