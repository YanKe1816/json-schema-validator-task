# json-schema-validator-task

## Input schema
```json
{
  "json": "object",
  "schema": "object"
}
```

## Output schema (`structuredContent`)
```json
{
  "valid": true,
  "errors": []
}
```

## Example cases
### 1. Direct valid
Input:
```json
{"json":{"a":1},"schema":{"a":"number"}}
```
Output:
```json
{"valid":true,"errors":[]}
```

### 2. Indirect valid
Input:
```json
{"json":{"a":1,"b":"x"},"schema":{"a":"number"}}
```
Output:
```json
{"valid":true,"errors":[]}
```

### 3. Invalid / out-of-scope
Input:
```json
{"json":{"a":"x"},"schema":{"a":"number"}}
```
Output:
```json
{"error":{"code":"VALIDATION_ERROR","message":"a must be number"}}
```
