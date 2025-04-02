# tvm_client.py
import requests
import json
import boto3
import base64

class TVMClient:
    def __init__(self, issuer, client_id, client_secret, role_arn, region):
        self.issuer = issuer.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.role_arn = role_arn
        self.region = region
        
    def get_token(self, email):
        """Get a token from the TVM issuer"""
        token_url = f"{self.issuer}/token"
        
        # For TVM approach, we're using the allowed domains approach
        # This might require adding our domain to the allowed list in the TVM
        data = {
            "email": email
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Using Basic Auth with the client ID and secret
        auth = (self.client_id, self.client_secret)
        
        print(f"Calling TVM endpoint: {token_url}")
        print(f"With email: {email}")
        print(f"Using client ID: {self.client_id}")
        # Don't print the secret for security reasons
        
        response = requests.post(token_url, headers=headers, json=data, auth=auth)
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Failed to get token: {response.text}")
            raise Exception(f"Failed to get token: {response.text}")
            
        token_data = response.json()
        print("Successfully retrieved token")
        return token_data["id_token"]
    
    def get_sigv4_credentials(self, email):
        """Get SigV4 credentials using the token"""
        # Get token from TVM
        token = self.get_token(email)
        
        # Assume role with token
        print(f"Assuming role: {self.role_arn}")
        sts = boto3.client('sts', region_name=self.region)
        assumed_role = sts.assume_role_with_web_identity(
            RoleArn=self.role_arn,
            RoleSessionName=f"qbiz-session-{email.replace('@', '-').replace('.', '-')}",
            WebIdentityToken=token
        )
        
        print("Successfully assumed role")
        
        # Return credentials in format suitable for boto3.client
        credentials = {
            "aws_access_key_id": assumed_role["Credentials"]["AccessKeyId"],
            "aws_secret_access_key": assumed_role["Credentials"]["SecretAccessKey"],
            "aws_session_token": assumed_role["Credentials"]["SessionToken"],
            "region_name": self.region
        }
        
        return credentials