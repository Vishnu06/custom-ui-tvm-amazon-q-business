# q_index_mcp_server.py
import json
import logging
import os
from tvm_client import TVMClient
import boto3
import asyncio
import websockets

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Read configuration from cdk-outputs.json
try:
    with open('cdk-outputs.json') as f:
        cdk_outputs = json.load(f)
        stack_outputs = list(cdk_outputs.values())[0] if cdk_outputs else {}
        
    logger.info("Found values in cdk-outputs.json")
    
    # Extract values
    config = {
        'issuer': stack_outputs.get('IssuerUrlOutput', ''),
        'client_id': stack_outputs.get('QbizTVMClientID', ''),
        'role_arn': stack_outputs.get('QBizAssumeRoleARN', ''),
        'client_secret': stack_outputs.get('QbizTVMClientSecret', ''),
        'region': "us-east-1",
        'email': "test_user@example.com",
        'application_id': "10245813-a332-4117-bf9e-2b1d302c4aa1",
        'retriever_id': "866eb4a0-5922-4ec1-8122-b762af1b8af4"
    }
    
except Exception as e:
    logger.error(f"Error reading cdk-outputs.json: {e}")
    # Fallback to hardcoded values
    config = {
        'issuer': 'https://98p7qvcbfb.execute-api.us-east-1.amazonaws.com/prod/',
        'client_id': 'oidc-tvm-592995829936',
        'client_secret': 'c3f1f474fa86341096fab415',
        'role_arn': 'arn:aws:iam::592995829936:role/tvm-qbiz-custom-oidc-role',
        'region': 'us-east-1',
        'email': 'test_user@example.com',
        'application_id': '10245813-a332-4117-bf9e-2b1d302c4aa1',
        'retriever_id': '866eb4a0-5922-4ec1-8122-b762af1b8af4'
    }

# Initialize TVM client
token_client = TVMClient(
    issuer=config['issuer'],
    client_id=config['client_id'],
    client_secret=config['client_secret'],
    role_arn=config['role_arn'],
    region=config['region']
)

async def search_q_index(query, max_results=5):
    """Search Amazon Q index and return formatted results"""
    try:
        # Get credentials from TVM
        logger.info(f"Getting credentials for query: {query}")
        credentials = token_client.get_sigv4_credentials(email=config['email'])
        
        # Initialize Q Business client with TVM credentials
        qbiz = boto3.client("qbusiness", **credentials)
        
        # Prepare search parameters
        search_params = {
            'applicationId': config['application_id'],
            'contentSource': {
                'retriever': {
                    'retrieverId': config['retriever_id']
                }
            },
            'queryText': query,
            'maxResults': max_results
        }
        
        logger.info(f"Searching Amazon Q with query: {query}")
        
        # Call the SearchRelevantContent API
        search_response = qbiz.search_relevant_content(**search_params)
        
        # Process results
        relevant_contents = search_response.get('relevantContent', [])
        logger.info(f"Search successful! Found {len(relevant_contents)} results")
        
        # Format results for Claude to cite
        formatted_results = []
        for i, content in enumerate(relevant_contents):
            if 'content' in content and 'textContent' in content['content'] and 'text' in content['content']['textContent']:
                text_content = content['content']['textContent']['text']
                
                # Extract document attributes if available
                source = "Unknown"
                title = "Untitled"
                if 'documentAttributes' in content:
                    attrs = content['documentAttributes']
                    if 'source' in attrs and 'value' in attrs['source']:
                        source = attrs['source']['value']
                    if 'title' in attrs and 'value' in attrs['title']:
                        title = attrs['title']['value']
                
                formatted_results.append({
                    "document_id": i,
                    "content": text_content,
                    "metadata": {
                        "source": source,
                        "title": title
                    }
                })
        
        return {"results": formatted_results}
    
    except Exception as e:
        logger.error(f"Error searching Amazon Q: {str(e)}")
        return {"error": str(e)}

async def chat_with_q(message):
    """Chat with Amazon Q and get a response with citations"""
    try:
        # Get credentials from TVM
        logger.info(f"Getting credentials for chat: {message}")
        credentials = token_client.get_sigv4_credentials(email=config['email'])
        
        # Initialize Q Business client with TVM credentials
        qbiz = boto3.client("qbusiness", **credentials)
        
        # Call ChatSync API
        chat_params = {
            'applicationId': config['application_id'],
            'userMessage': message
        }
        
        logger.info(f"Sending message to Amazon Q: {message}")
        
        # Call the ChatSync API
        chat_response = qbiz.chat_sync(**chat_params)
        
        # Extract the response
        system_message = chat_response.get('systemMessage', 'No response from Amazon Q')
        
        # Format source attributions for Claude to cite
        sources = []
        for i, source in enumerate(chat_response.get('sourceAttributions', [])):
            sources.append({
                "document_id": i,
                "title": source.get('title', 'Unknown'),
                "url": source.get('url', ''),
                "snippet": source.get('snippet', '')
            })
        
        return {
            "response": system_message,
            "sources": sources
        }
    
    except Exception as e:
        logger.error(f"Error chatting with Amazon Q: {str(e)}")
        return {"error": str(e)}

async def handle_connection(websocket, path):
    """Handle WebSocket connections from Claude Desktop"""
    logger.info(f"New connection from Claude Desktop at {path}")
    
    async for message in websocket:
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            # Handle tool discovery
            if message_type == "discover":
                logger.info("Received tool discovery request")
                
                # Define available tools
                tools = [
                    {
                        "name": "search_amazon_q",
                        "description": "Searches Amazon Q Business index for relevant information",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string", 
                                    "description": "The search query to find information in the enterprise data"
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "Maximum number of results to return (default: 5)"
                                }
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "chat_with_amazon_q",
                        "description": "Sends a message to Amazon Q Business and gets a response with citations",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "The message to send to Amazon Q"
                                }
                            },
                            "required": ["message"]
                        }
                    }
                ]
                
                # Send tool descriptions back to Claude
                response = {
                    "type": "discover_response",
                    "tools": tools
                }
                await websocket.send(json.dumps(response))
                logger.info("Sent tool descriptions to Claude")
            
            # Handle tool calls
            elif message_type == "call":
                logger.info("Received tool call request")
                
                tool_name = data.get("tool")
                call_id = data.get("id")
                params = data.get("params", {})
                
                # Call the appropriate tool
                if tool_name == "search_amazon_q":
                    query = params.get("query")
                    max_results = params.get("max_results", 5)
                    
                    logger.info(f"Calling search_amazon_q with query: {query}")
                    result = await search_q_index(query, max_results)
                    
                    # Send the result back to Claude
                    response = {
                        "type": "call_response",
                        "id": call_id,
                        "result": result
                    }
                    await websocket.send(json.dumps(response))
                    logger.info("Sent search results to Claude")
                
                elif tool_name == "chat_with_amazon_q":
                    message = params.get("message")
                    
                    logger.info(f"Calling chat_with_amazon_q with message: {message}")
                    result = await chat_with_q(message)
                    
                    # Send the result back to Claude
                    response = {
                        "type": "call_response",
                        "id": call_id,
                        "result": result
                    }
                    await websocket.send(json.dumps(response))
                    logger.info("Sent chat response to Claude")
                
                else:
                    logger.error(f"Unknown tool: {tool_name}")
                    
                    # Send error response
                    response = {
                        "type": "call_response",
                        "id": call_id,
                        "result": {"error": f"Unknown tool: {tool_name}"}
                    }
                    await websocket.send(json.dumps(response))
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
        
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")

async def main():
    """Start the MCP server"""
    # Standard MCP port for Claude Desktop is 8080
    server = await websockets.serve(handle_connection, "localhost", 8080)
    
    logger.info("MCP server started on localhost:8080")
    logger.info("Waiting for Claude Desktop to connect...")
    
    # Keep the server running
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())