Setting up local enzyme finance protocol instance for testing

## Test

1. Setup local account
```
>>> brownie accounts generate deployment_account
```

2. Create `.env` file containing `WEB3_INFURA_PROJECT_ID`

3. Add Etherscan API key

```
>>> brownie networks modify mainnet-fork explorer="https://api.etherscan.io/api?apikey=PTI588QGBZQWZ9RAF24C5UETQYHME6ZV45"
```
