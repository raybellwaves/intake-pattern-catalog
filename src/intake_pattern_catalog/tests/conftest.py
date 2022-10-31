import os
from typing import Callable
from unittest.mock import MagicMock

import aiobotocore.awsrequest
import aiobotocore.endpoint
import aiohttp
import aiohttp.client_reqrep
import aiohttp.typedefs
import boto3
import botocore.awsrequest
import botocore.model
import pytest
from moto import mock_s3


# This is necessary because of this issue
# https://github.com/aio-libs/aiobotocore/issues/755
# copied from https://gist.github.com/giles-betteromics/12e68b88e261402fbe31c2e918ea4168
class MockAWSResponse(aiobotocore.awsrequest.AioAWSResponse):
    def __init__(self, response: botocore.awsrequest.AWSResponse):
        self._moto_response = response
        self.status_code = response.status_code
        self.raw = MockHttpClientResponse(response)

    # adapt async methods to use moto's response
    async def _content_prop(self) -> bytes:
        return self._moto_response.content

    async def _text_prop(self) -> str:
        return self._moto_response.text


class MockHttpClientResponse(aiohttp.client_reqrep.ClientResponse):
    def __init__(self, response: botocore.awsrequest.AWSResponse):
        async def read(self, n: int = -1) -> bytes:
            # streaming/range requests. used by s3fs
            return response.content

        self.content = MagicMock(aiohttp.StreamReader)
        self.content.read = read
        self.response = response

    @property
    def raw_headers(self) -> aiohttp.typedefs.RawHeaders:
        # Return the headers encoded the way that aiobotocore expects them
        return {
            k.encode("utf-8"): str(v).encode("utf-8")
            for k, v in self.response.headers.items()
        }.items()


def patch_aiobotocore():
    def factory(original: Callable) -> Callable:
        def patched_convert_to_response_dict(
            http_response: botocore.awsrequest.AWSResponse, operation_model: botocore.model.OperationModel
        ):
            return original(MockAWSResponse(http_response), operation_model)

        return patched_convert_to_response_dict

    aiobotocore.endpoint.convert_to_response_dict = factory(aiobotocore.endpoint.convert_to_response_dict)

aiobotocore.endpoint.convert_to_response_dict = patch_aiobotocore()


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture(scope="function")
def s3(aws_credentials):
    with mock_s3():
        yield boto3.client("s3", region_name="us-east-1")
