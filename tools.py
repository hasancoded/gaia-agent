import os
import requests
from tavily import TavilyClient


class WebSearchTool:
    """Tool to search the web for information"""
    
    def __init__(self):
        self.api_key = os.environ.get("TAVILY_API_KEY")
        if self.api_key:
            self.client = TavilyClient(api_key=self.api_key)
        else:
            print("⚠️ Warning: TAVILY_API_KEY not found")
            self.client = None
    
    def search(self, query, max_results=8):
        """
        Search the web and return results
        
        Args:
            query: What to search for
            max_results: How many results to return
            
        Returns:
            String with search results
        """
        if not self.client:
            return "Web search unavailable - API key not configured"
        
        try:
            print(f"      Searching for: {query}")
            response = self.client.search(
                query=query,
                max_results=max_results
            )
            
            # Format results into readable text
            results_text = f"Search results for '{query}':\n\n"
            
            for i, result in enumerate(response.get('results', []), 1):
                title = result.get('title', 'No title')
                content = result.get('content', 'No content')
                url = result.get('url', 'No URL')
                
                results_text += f"Result {i}:\n"
                results_text += f"Title: {title}\n"
                results_text += f"Content: {content}\n"
                results_text += f"URL: {url}\n"
                results_text += "-" * 50 + "\n\n"
            
            return results_text
            
        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            print(f"      [ERROR] {error_msg}")
            return error_msg


class FileReaderTool:
    """Tool to read files from GAIA questions"""
    
    def __init__(self, gaia_api_url):
        self.api_url = gaia_api_url
        self._file_cache = {}  # Cache downloaded files
    
    def read_file(self, task_id, file_name=None):
        """
        Download and read a file associated with a GAIA question
        
        Args:
            task_id: The ID of the GAIA task
            file_name: Optional file name from question data
            
        Returns:
            File content as bytes, or None if download fails
        """
        # Return cached file if available
        if task_id in self._file_cache:
            print(f"      ✓ Using cached file for {task_id}")
            return self._file_cache[task_id]
        
        # GAIA API uses /files/{task_id} endpoint
        url = f"{self.api_url}/files/{task_id}"
        
        if file_name:
            print(f"      File name: {file_name}")
        
        # Try downloading with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"      Downloading from: {url}" + (f" (attempt {attempt + 1})" if attempt > 0 else ""))
                
                response = requests.get(url, timeout=60)
                
                # Check HTTP status first
                if response.status_code == 404:
                    print(f"      ⚠️  File not found (404)")
                    return None
                
                if response.status_code != 200:
                    print(f"      ⚠️  HTTP {response.status_code}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)
                        continue
                    return None
                
                # Check for empty response
                if len(response.content) == 0:
                    print(f"      ⚠️  Empty response")
                    return None
                
                # Check if response is JSON error message
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    try:
                        error_data = response.json()
                        if 'detail' in error_data:
                            error_msg = error_data['detail']
                            print(f"      ⚠️  API Error: {error_msg}")
                            return None
                    except:
                        pass
                
                # Success - cache and return
                print(f"      ✓ File downloaded successfully ({len(response.content)} bytes)")
                self._file_cache[task_id] = response.content
                return response.content
                    
            except requests.exceptions.Timeout:
                print(f"      ⚠️  Download timed out")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                    continue
                return None
            except Exception as e:
                print(f"      ✗ Error: {str(e)}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
                    continue
                return None
        
        return None


class CalculatorTool:
    """Tool to perform mathematical calculations"""
    
    def calculate(self, expression):
        """
        Safely evaluate a mathematical expression
        
        Args:
            expression: Math expression as string (e.g., "2 + 2")
            
        Returns:
            Result of calculation as string
        """
        try:
            # Only allow safe characters
            allowed_chars = set("0123456789+-*/().() ")
            if not all(c in allowed_chars for c in expression):
                return "Error: Invalid characters in expression"
            
            result = eval(expression)
            return str(result)
            
        except Exception as e:
            return f"Calculation error: {str(e)}"