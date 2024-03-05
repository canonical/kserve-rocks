## Testing

### Instructions

Test the storage-initializer by downloading one of the sample kserve models from google storage:
```
docker run storage-initializer:<version> gs://kfserving-examples/models/xgboost/iris /work
```

We should see:
```
INFO:root:Successfully copied gs://kfserving-examples/models/xgboost/iris to /work/stuff
```

In the logs (some other warnings may occur, but they're normal).  To further test, you can also
shell into the container while it is running and confirm the file is saved. 
