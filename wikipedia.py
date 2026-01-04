import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import sys
import os

# Add the parent directory to the Python path to import ai
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai import AIModel

def get_wikipedia_content(url):
    """
    Fetches the main content of a Wikipedia page using Selenium.
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(url)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        content_div = soup.find(id='mw-content-text')
        if content_div:
            # Get all the text from the content div
            text = content_div.get_text()
            return text
        return "Could not find content."
    finally:
        driver.quit()

def analyze_content(content):
    """
    Analyzes the content using the AI model and returns JSON details.
    """
    ai_model = AIModel()
    if not ai_model.llm:
        return {"error": "AI Model not loaded."}

    word_count = len(content.split())

    # Create a prompt for the AI
    prompt = f"""
    Analyze the following Wikipedia page content and provide a summary of its detail level.
    The content is:
    ---
    {content[:4000]}
    ---
    Based on the text, would you say the page is very detailed, moderately detailed, or not very detailed?
    Provide your answer in a JSON format with the keys "detail_level" and "summary".
    """

    generation_params = {} # Use default generation params
    response_stream = ai_model.ask(prompt, None, generation_params)
    
    ai_response = "".join(response_stream)
    
    try:
        # Attempt to parse the AI's response as JSON
        ai_json = json.loads(ai_response)
        detail_level = ai_json.get("detail_level", "N/A")
        summary = ai_json.get("summary", "N/A")
    except json.JSONDecodeError:
        # If the AI response is not valid JSON, handle it gracefully
        detail_level = "N/A"
        summary = ai_response


    return {
        "word_count": word_count,
        "detail_level": detail_level,
        "summary": summary
    }

if __name__ == '__main__':
    if len(sys.argv) > 1:
        wiki_url = sys.argv[1]
        print(f"Fetching content from: {wiki_url}")
        page_content = get_wikipedia_content(wiki_url)
        
        if "Could not find content." in page_content:
            print(json.dumps({"error": "Failed to retrieve content from the URL."}))
        else:
            print("Analyzing content...")
            analysis_results = analyze_content(page_content)
            print(json.dumps(analysis_results, indent=4))
    else:
        print("Please provide a Wikipedia URL as a command-line argument.")

