import boto3
import requests
import json
import base64
import os
from pprint import pprint

# Get values from cdk-outputs.json
try:
    # Try to read from cdk-outputs.json
    with open('cdk-outputs.json') as f:
        cdk_outputs = json.load(f)
        stack_outputs = cdk_outputs.get('TVMOidcIssuerStack', {})
        
        issuer = stack_outputs.get('IssuerUrlOutput', '').rstrip('/')
        client_id = stack_outputs.get('AudienceOutput', '')
        role_arn = stack_outputs.get('QBizAssumeRoleARN', '')
        client_secret = stack_outputs.get('TVMClientSecret', '')
        
        if not all([issuer, client_id, role_arn, client_secret]):
            print("Some values missing from cdk-outputs.json, please enter manually:")
            if not issuer:
                issuer = input("Enter Issuer URL (IssuerUrlOutput): ")
            if not client_id:
                client_id = input("Enter Client ID (AudienceOutput): ")
            if not role_arn:
                role_arn = input("Enter Role ARN (QBizAssumeRoleARN): ")
            if not client_secret:
                client_secret = input("Enter Client Secret (TVMClientSecret): ")
except Exception as e:
    print(f"Could not read cdk-outputs.json: {e}")
    issuer = input("Enter Issuer URL (IssuerUrlOutput): ")
    client_id = input("Enter Client ID (AudienceOutput): ")
    role_arn = input("Enter Role ARN (QBizAssumeRoleARN): ")
    client_secret = input("Enter Client Secret (TVMClientSecret): ")

region = "us-east-1"
email = "test_user@example.com"  # Can be any email

print(f"\nUsing the following configuration:")
print(f"Issuer URL: {issuer}")
print(f"Client ID: {client_id}")
print(f"Role ARN: {role_arn}")
print(f"Region: {region}")
print(f"Email: {email}")

# Get token from TVM
def get_token(issuer, client_id, client_secret, email):
    token_url = f"{issuer}/token"
    auth_string = f"{client_id}:{client_secret}"
    basic_auth_token = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {basic_auth_token}"
    }
    
    data = {
        "email": email
    }
    
    print(f"\nCalling TVM endpoint: {token_url}")
    response = requests.post(token_url, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Error calling TVM: Status code {response.status_code}")
        print(f"Response: {response.text}")
        return None
    
    print("Successfully received token from TVM")
    return response.json().get("id_token")

# Assume role with token
def assume_role_with_token(token, role_arn, region, email):
    sts = boto3.client('sts', region_name=region)
    
    try:
        print(f"\nAssuming role {role_arn} with token")
        assumed_role = sts.assume_role_with_web_identity(
            RoleArn=role_arn,
            RoleSessionName=f"qbiz-session-{email.replace('@', '-').replace('.', '-')}",
            WebIdentityToken=token
        )
        
        print("Successfully assumed role")
        return {
            "aws_access_key_id": assumed_role["Credentials"]["AccessKeyId"],
            "aws_secret_access_key": assumed_role["Credentials"]["SecretAccessKey"],
            "aws_session_token": assumed_role["Credentials"]["SessionToken"],
            "region_name": region
        }
    except Exception as e:
        print(f"Error assuming role: {e}")
        return None

# Call Amazon Q Business APIs
def call_q_business_apis(credentials):
    if not credentials:
        print("No credentials available")
        return
    
    try:
        print("\nInitializing Amazon Q Business client")
        qbiz = boto3.client("qbusiness", **credentials)
        
        # List applications
        print("\nListing Amazon Q Business applications:")
        response = qbiz.list_applications()
        
        if not response.get("applications"):
            print("No applications found")
            return
        
        print(f"Found {len(response['applications'])} applications:")
        for app in response['applications']:
            print(f"- {app.get('displayName', 'Unnamed')} (ID: {app.get('applicationId', 'Unknown')})")
        
        app_id = input("\nEnter application ID to test: ")
        
        # Try ChatSync
        print(f"\nTesting ChatSync API with application {app_id}")
        try:
            chat_response = qbiz.chat_sync(
                applicationId=app_id,
                userMessage="Tell me about Amazon Q Business"
            )
            
            print("ChatSync successful!")
            print(f"System message: {chat_response.get('systemMessage', 'No response')[:200]}...")
        except Exception as e:
            print(f"Error with ChatSync: {e}")
        
        # Try listing retrievers
        try:
            print(f"\nListing retrievers for application {app_id}")
            retrievers = qbiz.list_retrievers(applicationId=app_id)
            
            if not retrievers.get("retrievers"):
                print("No retrievers found")
                return
            
            print(f"Found {len(retrievers['retrievers'])} retrievers:")
            for retriever in retrievers['retrievers']:
                print(f"- {retriever.get('displayName', 'Unnamed')} (ID: {retriever.get('retrieverId', 'Unknown')})")
            
            retriever_id = retrievers['retrievers'][0]['retrieverId']
            
            # Try SearchRelevantContent
            print(f"\nTesting SearchRelevantContent API with retriever {retriever_id}")
            search_response = qbiz.search_relevant_content(
                applicationId=app_id,
                contentSource={
                    'retriever': {
                        'retrieverId': retriever_id
                    }
                },
                queryText="What is Amazon Q Business?",
                maxResults=3
            )
            
            print("SearchRelevantContent successful!")
            if search_response.get("relevantContent"):
                print(f"Found {len(search_response['relevantContent'])} relevant content items")
                for i, content in enumerate(search_response['relevantContent']):
                    print(f"\nContent {i+1}:")
                    print(f"Content snippet: {content.get('content', 'No content')[:100]}...")
            else:
                print("No relevant content found")
                
        except Exception as e:
            print(f"Error with retrievers or search: {e}")
            
    except Exception as e:
        print(f"Error initializing client or listing applications: {e}")

# Main flow
try:
    # Get token
    token = get_token(issuer, client_id, client_secret, email)
    if not token:
        print("Failed to get token, exiting")
        exit(1)
    
    # Assume role
    credentials = assume_role_with_token(token, role_arn, region, email)
    if not credentials:
        print("Failed to assume role, exiting")
        exit(1)
    
    # Call Q Business APIs
    call_q_business_apis(credentials)
    
except Exception as e:
    print(f"Unexpected error: {e}")