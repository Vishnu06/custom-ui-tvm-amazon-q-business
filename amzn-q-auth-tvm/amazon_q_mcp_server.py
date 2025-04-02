from mcp.server.fastmcp import FastMCP
import boto3
import logging
import sys
import json
from tvm_client import TVMClient

# Set up logging with ONLY stderr (no file handler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)  # Only log to stderr
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("amazon-q-business")

# Hardcoded configuration with your specified values
config = {
    'issuer': 'https://98p7qvcbfb.execute-api.us-east-1.amazonaws.com/prod/',
    'client_id': 'oidc-tvm-592995829936',
    'client_secret': 'c3f1f474fa86341096fab415',
    'role_arn': 'arn:aws:iam::592995829936:role/tvm-qbiz-custom-oidc-role',
    'region': 'us-east-1',
    'email': 'test_user@example.com',
    # Hardcoded app ID and retriever ID as specified
    'application_id': '10245813-a332-4117-bf9e-2b1d302c4aa1',  # QBusiness-application-c8239
    'retriever_id': '866eb4a0-5922-4ec1-8122-b762af1b8af4'     # plato-native-retriever-edce7a24-85f4-4559-a1e0-8ea913691a95
}

# Initialize your existing TVM client
token_client = TVMClient(
    issuer=config['issuer'],
    client_id=config['client_id'],
    client_secret=config['client_secret'],
    role_arn=config['role_arn'],
    region=config['region']
)

@mcp.tool()
async def search_q_index(query: str, max_results: int = 5) -> str:
    """Search Amazon Q Business index for relevant information.
    
    Args:
        query: The search query to find information
        max_results: Maximum number of results to return (default: 5)
    """
    try:
        logger.info(f"Getting credentials for query: {query}")
        # Get credentials using your existing TVM client
        credentials = token_client.get_sigv4_credentials(email=config['email'])
        
        # Initialize Q Business client with the credentials
        qbiz = boto3.client("qbusiness", **credentials)
        
        # Using the exact parameters format from your working test script
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
        
        logger.info(f"Searching Amazon Q with params: {json.dumps(search_params)}")
        
        try:
            # Call the SearchRelevantContent API
            search_response = qbiz.search_relevant_content(**search_params)
            
            # Log the response structure for debugging
            logger.info(f"Search response keys: {list(search_response.keys())}")
            
            # Check if we got results
            if 'relevantContent' in search_response:
                relevant_content = search_response['relevantContent']
                logger.info(f"Found {len(relevant_content)} results")
                
                if len(relevant_content) > 0:
                    # Log structure of first result for debugging
                    logger.info(f"First result keys: {list(relevant_content[0].keys())}")
                
                # Process results
                results = []
                for i, content in enumerate(relevant_content):
                    try:
                        # Extract content using the same approach as in your test script
                        if 'content' in content:
                            content_obj = content['content']
                            if isinstance(content_obj, dict) and 'textContent' in content_obj:
                                text_content = content_obj['textContent']
                                if isinstance(text_content, dict) and 'text' in text_content:
                                    result_text = text_content['text']
                                    # Add source information if available
                                    if 'documentAttributes' in content and 'title' in content['documentAttributes']:
                                        source = content['documentAttributes']['title']
                                        results.append(f"{result_text}\n\nSource: {source}")
                                    else:
                                        results.append(result_text)
                        else:
                            logger.warning(f"Result {i+1} doesn't have 'content' key")
                    except Exception as item_error:
                        logger.error(f"Error processing result {i+1}: {str(item_error)}")
                
                if results:
                    return "\n\n---\n\n".join(results)
                else:
                    # Try fallback extraction if the expected structure wasn't found
                    logger.warning("Expected content structure not found, trying alternative extraction")
                    fallback_results = []
                    for i, content in enumerate(relevant_content):
                        try:
                            # Log full content structure for debugging
                            logger.info(f"Content {i+1} structure: {json.dumps(content)[:200]}...")
                            # Just convert whatever we got to string as a fallback
                            fallback_results.append(f"Result {i+1}: {str(content)[:500]}...")
                        except Exception as e:
                            logger.error(f"Error in fallback extraction: {str(e)}")
                    
                    if fallback_results:
                        return "\n\n---\n\n".join(fallback_results)
                    else:
                        return "Found results but couldn't extract content. Check logs for details."
            else:
                logger.warning("No 'relevantContent' in search response")
                return "No search results found for your query."
                
        except Exception as search_error:
            logger.error(f"Search error: {type(search_error).__name__}: {str(search_error)}")
            
            # Try without maxResults (using your test script's fallback approach)
            logger.info("Trying search without maxResults parameter...")
            try:
                simplified_params = {
                    'applicationId': config['application_id'],
                    'contentSource': {
                        'retriever': {
                            'retrieverId': config['retriever_id']
                        }
                    },
                    'queryText': query
                }
                
                logger.info(f"Simplified params: {json.dumps(simplified_params)}")
                search_response = qbiz.search_relevant_content(**simplified_params)
                
                # Process results (same code as above)
                if 'relevantContent' in search_response:
                    relevant_content = search_response['relevantContent']
                    logger.info(f"Found {len(relevant_content)} results with simplified params")
                    
                    # Process results (simplified version)
                    results = []
                    for content in relevant_content:
                        if 'content' in content and isinstance(content['content'], dict):
                            content_obj = content['content']
                            if 'textContent' in content_obj and isinstance(content_obj['textContent'], dict):
                                if 'text' in content_obj['textContent']:
                                    results.append(content_obj['textContent']['text'])
                    
                    if results:
                        return "\n\n---\n\n".join(results)
                
                return "No results found with simplified search parameters."
            except Exception as simplified_error:
                logger.error(f"Simplified search error: {str(simplified_error)}")
                return f"Search API failed: {str(simplified_error)}"
    
    except Exception as e:
        logger.error(f"Overall error: {type(e).__name__}: {str(e)}")
        return f"Error searching Amazon Q: {type(e).__name__}: {str(e)}"

@mcp.tool()
async def chat_with_q(message: str) -> str:
    """Chat with Amazon Q Business.
    
    Args:
        message: The message to send to Amazon Q
    """
    try:
        logger.info(f"Getting credentials for chat: {message}")
        # Get credentials using your existing TVM client
        credentials = token_client.get_sigv4_credentials(email=config['email'])
        
        # Initialize Q Business client with the credentials
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
        
        # Format source attributions for better context
        source_info = []
        for i, source in enumerate(chat_response.get('sourceAttributions', [])):
            source_info.append(f"Source {i+1}: {source.get('title', 'Unknown')}")
            if 'snippet' in source:
                source_info.append(f"Snippet: {source['snippet'][:100]}...")
        
        if source_info:
            return f"{system_message}\n\nSources:\n" + "\n".join(source_info)
        else:
            return system_message
    
    except Exception as e:
        logger.error(f"Error chatting with Amazon Q: {str(e)}")
        return f"Error chatting with Amazon Q: {str(e)}"

# Only run the server if this file is executed directly
if __name__ == "__main__":
    logger.info("Starting Amazon Q MCP Server")
    # Run the server using STDIO transport (recommended for Claude Desktop)
    mcp.run(transport='stdio')