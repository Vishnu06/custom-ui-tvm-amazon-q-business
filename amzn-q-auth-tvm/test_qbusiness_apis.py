# test_qbusiness_apis.py
import json
from tvm_client import TVMClient
import boto3

# Get values from cdk-outputs.json
try:
    with open('cdk-outputs.json') as f:
        cdk_outputs = json.load(f)
        stack_outputs = list(cdk_outputs.values())[0] if cdk_outputs else {}
        
    print("Found values in cdk-outputs.json:")
    for key, value in stack_outputs.items():
        print(f"- {key}: {value}")
        
    # Extract correct values
    issuer = stack_outputs.get('IssuerUrlOutput', '')
    client_id = stack_outputs.get('QbizTVMClientID', '') 
    role_arn = stack_outputs.get('QBizAssumeRoleARN', '')
    client_secret = stack_outputs.get('QbizTVMClientSecret', '')
    
except Exception as e:
    print(f"Error reading cdk-outputs.json: {e}")
    issuer = input("Enter Issuer URL (IssuerUrlOutput): ")
    client_id = input("Enter Client ID (QbizTVMClientID): ")
    role_arn = input("Enter Role ARN (QBizAssumeRoleARN): ")
    client_secret = input("Enter Client Secret (QbizTVMClientSecret): ")

region = "us-east-1"
email = "test_user@example.com"

print("\nUsing configuration:")
print(f"Issuer: {issuer}")
print(f"Client ID: {client_id}")
print(f"Role ARN: {role_arn}")
print(f"Region: {region}")
print(f"Email: {email}")

# First, let's use regular AWS credentials to get app and retriever IDs
try:
    print("\nUsing regular AWS credentials to get application and retriever IDs...")
    regular_client = boto3.client('qbusiness', region_name=region)
    apps_response = regular_client.list_applications()
    
    if not apps_response.get("applications"):
        print("No applications found with regular credentials")
        app_id = input("Enter your Q Business application ID manually: ")
        retriever_id = input("Enter your Q Business retriever ID manually: ")
    else:
        print("Applications found with regular credentials:")
        for i, app in enumerate(apps_response['applications']):
            print(f"{i+1}. {app.get('displayName', 'Unnamed')} (ID: {app.get('applicationId', 'Unknown')})")
        
        app_index = int(input("\nEnter the number of the application to use: ")) - 1
        app_id = apps_response['applications'][app_index]['applicationId']
        
        retrievers_response = regular_client.list_retrievers(applicationId=app_id)
        if not retrievers_response.get("retrievers"):
            print("No retrievers found for this application")
            retriever_id = input("Enter your Q Business retriever ID manually: ")
        else:
            print("\nRetrievers found for this application:")
            for i, retriever in enumerate(retrievers_response['retrievers']):
                print(f"{i+1}. {retriever.get('displayName', 'Unnamed')} (ID: {retriever.get('retrieverId', 'Unknown')})")
            
            retriever_index = int(input("\nEnter the number of the retriever to use: ")) - 1
            retriever_id = retrievers_response['retrievers'][retriever_index]['retrieverId']
    
    print(f"\nSelected application ID: {app_id}")
    print(f"Selected retriever ID: {retriever_id}")
    
    # Get more information about the application
    try:
        app_details = regular_client.get_application(applicationId=app_id)
        print(f"\nApplication details:")
        print(f"Status: {app_details.get('status', 'Unknown')}")
        print(f"Identity type: {app_details.get('identityType', 'Unknown')}")
        
        # Get retriever details
        try:
            retriever_details = regular_client.get_retriever(applicationId=app_id, retrieverId=retriever_id)
            print(f"\nRetriever details:")
            print(f"Status: {retriever_details.get('status', 'Unknown')}")
            print(f"Type: {retriever_details.get('type', 'Unknown')}")
            
            # Get the Kendra index ID if this is a Kendra index type retriever
            kendra_index_id = None
            if retriever_details.get('type') == 'KENDRA_INDEX':
                if 'configuration' in retriever_details and 'kendraIndexConfiguration' in retriever_details['configuration']:
                    kendra_index_id = retriever_details['configuration']['kendraIndexConfiguration'].get('indexId')
                    print(f"Kendra Index ID: {kendra_index_id}")
            
        except Exception as e:
            print(f"Error getting retriever details: {e}")
            
    except Exception as e:
        print(f"Error getting application details: {e}")
        
except Exception as e:
    print(f"Error getting application/retriever IDs with regular credentials: {e}")
    app_id = input("Enter your Q Business application ID manually: ")
    retriever_id = input("Enter your Q Business retriever ID manually: ")

# Initialize TVM client
token_client = TVMClient(
    issuer=issuer,
    client_id=client_id,
    client_secret=client_secret,
    role_arn=role_arn,
    region=region
)

# Try to get credentials and call specific APIs
try:
    print("\nGetting credentials from TVM...")
    credentials = token_client.get_sigv4_credentials(email=email)
    print("Successfully got credentials!")
    
    # Initialize Q Business client with TVM credentials
    qbiz = boto3.client("qbusiness", **credentials)
    
    # Test SearchRelevantContent API
    query = input("\nEnter a query for testing: ")
    print(f"\nTesting SearchRelevantContent API with query: '{query}'")
    
    # Try with retriever
    try:
        search_params = {
            'applicationId': app_id,
            'contentSource': {
                'retriever': {
                    'retrieverId': retriever_id
                }
            },
            'queryText': query,
            'maxResults': 5
        }
        
        print(f"SearchRelevantContent request parameters: {json.dumps(search_params, indent=2)}")
        search_response = qbiz.search_relevant_content(**search_params)
        
        print(f"Search successful! Found {len(search_response.get('relevantContent', []))} results")
        
        for i, content in enumerate(search_response.get('relevantContent', [])):
            print(f"\nResult {i+1}:")
            if 'content' in content:
                print(f"Content: {content['content']}")
            else:
                print("No content available")
            
    except Exception as e:
        print(f"Error with retriever-based SearchRelevantContent: {e}")
        
        # Try an alternate approach using the same retriever ID but without the maxResults param
        print("\nTrying SearchRelevantContent with simplified parameters...")
        try:
            simplified_params = {
                'applicationId': app_id,
                'contentSource': {
                    'retriever': {
                        'retrieverId': retriever_id
                    }
                },
                'queryText': query
            }
            
            print(f"Simplified request parameters: {json.dumps(simplified_params, indent=2)}")
            search_response = qbiz.search_relevant_content(**simplified_params)
            
            print(f"Search successful! Found {len(search_response.get('relevantContent', []))} results")
            
            for i, content in enumerate(search_response.get('relevantContent', [])):
                print(f"\nResult {i+1}:")
                if 'content' in content:
                    print(f"Content: {content['content']}")
                else:
                    print("No content available")
                    
        except Exception as e:
            print(f"Error with simplified SearchRelevantContent: {e}")
            
            # Let's retry with a hardcoded retriever ID to verify
            print("\nTrying with hardcoded retriever ID...")
            try:
                hardcoded_params = {
                    'applicationId': app_id,
                    'contentSource': {
                        'retriever': {
                            'retrieverId': "92a832b7-8d36-449b-8f24-aa027ea9b917"  # Hardcoded retriever ID
                        }
                    },
                    'queryText': query
                }
                
                print(f"Hardcoded request parameters: {json.dumps(hardcoded_params, indent=2)}")
                search_response = qbiz.search_relevant_content(**hardcoded_params)
                
                print(f"Search successful with hardcoded ID! Found {len(search_response.get('relevantContent', []))} results")
                
                for i, content in enumerate(search_response.get('relevantContent', [])):
                    print(f"\nResult {i+1}:")
                    if 'content' in content:
                        print(f"Content: {content['content']}")
                    else:
                        print("No content available")
                
            except Exception as e:
                print(f"Error with hardcoded retriever ID: {e}")
    
    # Test ChatSync API
    print("\nTesting ChatSync API...")
    try:
        chat_response = qbiz.chat_sync(
            applicationId=app_id,
            userMessage=query
        )
        
        print("ChatSync successful!")
        if 'systemMessage' in chat_response:
            print(f"System message (full response):")
            print(f"{chat_response['systemMessage']}")
        else:
            print("No system message in response")
            
        if 'sourceAttributions' in chat_response:
            print("\nSource attributions:")
            for i, source in enumerate(chat_response['sourceAttributions']):
                print(f"Source {i+1}:")
                print(f"Title: {source.get('title', 'N/A')}")
                print(f"URL: {source.get('url', 'N/A')}")
                if 'snippet' in source:
                    print(f"Snippet: {source['snippet'][:100]}...")
        
    except Exception as e:
        print(f"Error with ChatSync: {e}")

except Exception as e:
    print(f"Error: {e}")