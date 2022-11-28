Setting up local enzyme finance protocol instance for testing

## Test

Setup local account
```
brownie accounts generate deployment_account
```
Create `.env` file containing `WEB3_INFURA_PROJECT_ID`

Add Etherscan API key

`brownie networks modify mainnet-fork explorer=https://api.etherscan.io/api?apikey=PTI588QGBZQWZ9RAF24C5UETQYHME6ZV45`
