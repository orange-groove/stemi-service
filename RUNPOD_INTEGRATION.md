# RunPod Integration

This service now supports stem separation using RunPod's GPU-powered separation service as an alternative to local processing.

## Setup

1. **Set your RunPod API key:**
   ```bash
   export RUNPOD_API_KEY="your_runpod_api_key_here"
   ```

2. **Optional: Set custom endpoint ID:**
   ```bash
   export RUNPOD_ENDPOINT_ID="your_endpoint_id"  # defaults to "maxm6b2amueuny"
   ```

## How it Works

The integration automatically:

1. **Encodes** your audio file to base64
2. **Submits** the separation job to RunPod API
3. **Polls** for completion (up to 5 minutes by default)
4. **Downloads** the separated stems from Supabase URLs
5. **Fails** if RunPod is unavailable or processing fails

## API Flow

### Submit Job
```bash
curl -X POST https://api.runpod.ai/v2/maxm6b2amueuny/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{"input": {"audio_file": "$AUDIO_B64", "stems": ["vocals", "drums"]}}'
```

### Check Status
```bash
curl -s -X GET "https://api.runpod.ai/v2/maxm6b2amueuny/status/$JOB_ID" \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Configuration

The integration is configured in `flaskr/config.py`:

```python
RUNPOD_API_KEY = os.getenv('RUNPOD_API_KEY')
RUNPOD_ENDPOINT_ID = os.getenv('RUNPOD_ENDPOINT_ID', 'maxm6b2amueuny')
```

## Testing

Run the test script to verify the integration:

```bash
python test_runpod_integration.py
```

## Error Handling

The service will fail if:
- RunPod API key is not configured
- RunPod service is unavailable
- Processing times out (5 minutes default)
- Any other RunPod-related error occurs

**No fallback to local processing** - RunPod must succeed or the request fails.

## Benefits

- **GPU Acceleration**: Leverages RunPod's powerful GPU infrastructure
- **Scalability**: Offloads CPU-intensive processing
- **Simplicity**: Single processing path with clear error handling
- **Cost Efficiency**: Pay only for GPU time used
