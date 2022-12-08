Setting up local enzyme finance protocol instance for testing

## Testing

1. Setup local account
```
>>> brownie accounts generate deployment_account
```

2. Create `.env` file containing:
- `WEB3_INFURA_PROJECT_ID`
- `ETHERSCAN_TOKEN`

3. Run
```
brownie test --network mainnet-fork
```
