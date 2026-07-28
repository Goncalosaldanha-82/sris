import os,sys,boto3
p=sys.argv[1]
if not os.getenv("OBJECT_STORAGE_ENDPOINT"): raise SystemExit(0)
s3=boto3.client("s3",endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY"),aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_KEY"),region_name=os.getenv("OBJECT_STORAGE_REGION","eu-west-1"))
b=os.getenv("OBJECT_STORAGE_BUCKET","sris-backups")
try:s3.head_bucket(Bucket=b)
except Exception:s3.create_bucket(Bucket=b)
s3.upload_file(p,b,os.path.basename(p),ExtraArgs={"ServerSideEncryption":"AES256"})
print("uploaded",p)
