# SYNOP FM-12 Surface Code Decoder
A Python decoder for WMO SYNOP FM-12 surface weather observation codes.

## Features
- Decode single SYNOP messages
- Batch decode mixed text files
- FOG / TS / TSRA full descriptions
- W1/W2 past weather (Code 26)
- TOML config file
- REST API (Flask)
- JSON and TXT output

## Usage
synop decode AAXX 06091 43279 32597 31410 10390 20264 30018 40035 83400 333 10264
synop batch -f messages.txt
synop encode
synop config
synop api
