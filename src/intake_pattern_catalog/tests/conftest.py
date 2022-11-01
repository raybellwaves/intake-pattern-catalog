# copied from https://github.com/fsspec/s3fs/blob/main/s3fs/tests/test_s3fs.py
import json
import os
import time

import pytest
import requests
from s3fs import S3FileSystem

test_bucket_name = "test"
secure_bucket_name = "test-secure"
versioned_bucket_name = "test-versioned"

port = 5555
endpoint_uri = "http://127.0.0.1:%s/" % port


@pytest.fixture()
def s3_base():
    # writable local S3 system
    import shlex
    import subprocess

    try:
        # should fail since we didn't start server yet
        r = requests.get(endpoint_uri)
    except BaseException:
        pass
    else:
        if r.ok:
            raise RuntimeError("moto server already up")
    if "AWS_SECRET_ACCESS_KEY" not in os.environ:
        os.environ["AWS_SECRET_ACCESS_KEY"] = "foo"
    if "AWS_ACCESS_KEY_ID" not in os.environ:
        os.environ["AWS_ACCESS_KEY_ID"] = "foo"
    proc = subprocess.Popen(
        shlex.split("moto_server s3 -p %s" % port),
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    timeout = 5
    while timeout > 0:
        try:
            print("polling for moto server")
            r = requests.get(endpoint_uri)
            if r.ok:
                break
        except BaseException:
            pass
        timeout -= 0.1
        time.sleep(0.1)
    print("server up")
    yield
    print("moto done")
    proc.terminate()
    proc.wait()


def get_boto3_client():
    from botocore.session import Session

    # NB: we use the sync botocore client for setup
    session = Session()
    return session.create_client("s3", endpoint_url=endpoint_uri)


@pytest.fixture()
def s3(s3_base):
    client = get_boto3_client()
    client.create_bucket(Bucket=test_bucket_name, ACL="public-read")

    client.create_bucket(Bucket=versioned_bucket_name, ACL="public-read")
    client.put_bucket_versioning(
        Bucket=versioned_bucket_name, VersioningConfiguration={"Status": "Enabled"}
    )

    # initialize secure bucket
    client.create_bucket(Bucket=secure_bucket_name, ACL="public-read")
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Id": "PutObjPolicy",
            "Statement": [
                {
                    "Sid": "DenyUnEncryptedObjectUploads",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:PutObject",
                    "Resource": "arn:aws:s3:::{bucket_name}/*".format(
                        bucket_name=secure_bucket_name
                    ),
                    "Condition": {
                        "StringNotEquals": {
                            "s3:x-amz-server-side-encryption": "aws:kms"
                        }
                    },
                }
            ],
        }
    )
    client.put_bucket_policy(Bucket=secure_bucket_name, Policy=policy)

    S3FileSystem.clear_instance_cache()
    s3 = S3FileSystem(anon=False, client_kwargs={"endpoint_url": endpoint_uri})
    s3.invalidate_cache()
    yield s3
