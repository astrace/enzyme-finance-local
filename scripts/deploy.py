from brownie import (
    Dispatcher, GasRelayPaymasterLib, #BeaconProxyFactory,
    GasRelayPaymasterFactory, FundDeployer, ValueInterpreter,
    ExternalPositionFactory, PolicyManager, FeeManager,
    IntegrationManager, PolicyManager, ComptrollerLib,
    ProtocolFeeReserveLib, ExternalPositionManager,
    ProtocolFeeTracker, VaultLib, ProtocolFeeTracker,
    accounts
)

ONE_DAY_IN_SECONDS = 86_400

USDT = "0x55d398326f99059ff775485246999027b3197955"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
MLN = "0xec67005c4e498ec7f55e092bd1d35cbc47c91892"

# GSN
RELAY_HUB = "0x9e59Ea5333cD4f402dAc320a04fafA023fe3810D"
TRUSTED_FORWARDER = "0xAa3E82b4c4093b4bA13Cb5714382C99ADBf750cA"

def main():
    acct = accounts.load('deployment_account')
    d = {'from': acct}

    dispatcher = Dispatcher.deploy({'from': acct})
    gas_relay_paymaster_lib = GasRelayPaymasterLib.deploy(WETH, RELAY_HUB, TRUSTED_FORWARDER, d)

    gas_relay_paymaster_factory = GasRelayPaymasterFactory.deploy(dispatcher, gas_relay_paymaster_lib, d)
    fund_deployer = FundDeployer.deploy(dispatcher, gas_relay_paymaster_factory, d)

    # set current fund deployer
    dispatcher.setCurrentFundDeployer(fund_deployer, d)

    # input addresses needed for deploying ComptrollerLib
    protocol_fee_reserve = ProtocolFeeReserveLib.deploy(d)
    value_interpreter = ValueInterpreter.deploy(fund_deployer, WETH, ONE_DAY_IN_SECONDS, d)
    
    external_position_factory = ExternalPositionFactory.deploy(dispatcher, d)
    policy_manager = PolicyManager.deploy(fund_deployer, gas_relay_paymaster_factory, d)
    external_position_manager = ExternalPositionManager.deploy(fund_deployer, external_position_factory, policy_manager, d)

    fee_manager = FeeManager.deploy(fund_deployer, d)

    integration_manager = IntegrationManager.deploy(fund_deployer, policy_manager, value_interpreter, d)

    policy_manager = PolicyManager.deploy(fund_deployer, gas_relay_paymaster_factory, d)

    comptroller_lib = ComptrollerLib.deploy(
        dispatcher,
        protocol_fee_reserve,
        fund_deployer,
        value_interpreter,
        external_position_manager,
        fee_manager,
        integration_manager,
        policy_manager,
        gas_relay_paymaster_factory,
        MLN,
        WETH,
        d
    )

    # set comptroller lib
    fund_deployer.setComptrollerLib(comptroller_lib, d)

    # set protocol fee tracker
    protocol_fee_tracker = ProtocolFeeTracker.deploy(fund_deployer, d)
    fund_deployer.setProtocolFeeTracker(protocol_fee_tracker, d)

    """
    constructor(
        address _externalPositionManager,
        address _gasRelayPaymasterFactory,
        address _protocolFeeReserve,
        address _protocolFeeTracker,
        address _mlnToken,
        address _mlnBurner,
        address _wethToken,
        uint256 _positionsLimit
    """

    # set vault lib
    vault_lib = VaultLib.deploy(
        external_position_manager,
        gas_relay_paymaster_factory,
        protocol_fee_reserve,
        protocol_fee_tracker,
        MLN,
        "0x0000000000000000000000000000000000000000",
        WETH,
        1_000_000,
        d
    )
    fund_deployer.setVaultLib(vault_lib, d)

    # set release live
    fund_deployer.setReleaseLive(d)

    result = fund_deployer.createNewFund(
        accounts[0], "MyFund", "XYZ", WETH, 0, "", "",
        {"from": accounts[0]}
    )

    print("RESULT", result)
