import json
import sys
import os
from SPARQLWrapper import SPARQLWrapper, JSON

# Add the parent directory to the Python path to import ai
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai import AIModel

def get_city_data():
    """
    Queries Wikidata for cities with a population greater than 30,000.
    """
    endpoint_url = "https://query.wikidata.org/sparql"

    # The SPARQL query gets cities, their population, country, and coordinates.
    # We limit it to 25 for this example to avoid very long run times.
    query = """
    SELECT ?cityLabel ?countryLabel ?population ?location WHERE {
      ?city wdt:P31/wdt:P279* wd:Q515.  # instance of a city
      ?city wdt:P1082 ?population.
      FILTER(?population > 30000).
      ?city wdt:P17 ?country.
      ?city wdt:P625 ?location.
      SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
    }
    LIMIT 5
    """

    sparql = SPARQLWrapper(endpoint_url)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    try:
        results = sparql.query().convert()
        return results["results"]["bindings"]
    except Exception as e:
        print(f"Error querying Wikidata: {e}")
        return None

def analyze_city_data(city_data, ai_model):
    """
    Analyzes a single city's data for correctness using the AI model.
    """
    if not ai_model.llm:
        return {"error": "AI Model not loaded."}

    # Format the city data for the prompt
    city_name = city_data.get('cityLabel', {}).get('value', 'N/A')
    country_name = city_data.get('countryLabel', {}).get('value', 'N/A')
    population = city_data.get('population', {}).get('value', 'N/A')
    location = city_data.get('location', {}).get('value', 'N/A')

    prompt_data = {
        "city": city_name,
        "country": country_name,
        "population": population,
        "coordinates": location
    }

    prompt = f"""
    As a data validator, analyze the following city data for obvious inconsistencies.
    - Does the coordinate location make sense for the city and country?
    - Does the population figure seem plausible for this city, or is it obviously incorrect (e.g., a tiny village with millions of people, or a major metropolis with a population of 100)?

    Provide your analysis in a JSON format with three keys:
    1. "is_consistent" (boolean): true if the coordinates and country seem correct.
    2. "population_plausible" (boolean): true if the population number seems reasonable.
    3. "reason" (string): a brief explanation if any inconsistencies are found.

    Data:
    {json.dumps(prompt_data, indent=2)}
    """

    generation_params = {
        "temperature": 0.2, # Lower temperature for more deterministic, factual output
        "max_tokens": 256
    }
    response_stream = ai_model.ask(prompt, "You are a helpful data validation assistant that provides responses in JSON format.", generation_params)
    ai_response = "".join(response_stream)

    try:
        # Clean up the response to extract only the JSON part
        json_response_str = ai_response[ai_response.find('{'):ai_response.rfind('}')+1]
        analysis = json.loads(json_response_str)
    except json.JSONDecodeError:
        analysis = {
            "is_consistent": "unknown",
            "population_plausible": "unknown",
            "reason": f"Could not parse AI response: {ai_response}"
        }
    
    return {
        "city": city_name,
        "checked_data": prompt_data,
        "analysis": analysis
    }

def print_results_table(results):
    """
    Prints the analysis results in a formatted table.
    """
    print("\n\n--- Analysis Summary Table ---")
    headers = ["City", "Country", "Population", "Coords OK?", "Pop. OK?"]
    
    # Simple formatting: create a format string
    row_format = "{:<25} | {:<20} | {:<15} | {:<12} | {:<12}"
    
    print(row_format.format(*headers))
    print("-" * 95)

    for res in results:
        city = res.get('city', 'N/A')
        country = res.get('checked_data', {}).get('country', 'N/A')
        population = res.get('checked_data', {}).get('population', 'N/A')
        
        analysis = res.get('analysis', {})
        is_consistent = str(analysis.get('is_consistent', '?'))
        pop_plausible = str(analysis.get('population_plausible', '?'))

        print(row_format.format(city, country, population, is_consistent, pop_plausible))


if __name__ == '__main__':
    print("--> Wikidata Validator: Initializing AI Model...")
    ai_model = AIModel()
    if not ai_model.llm:
        print("!!! FATAL: Could not load AI Model. Exiting.")
        exit()

    print("--> Wikidata Validator: Fetching city data from Wikidata...")
    cities = get_city_data()

    if cities:
        print(f"--> Wikidata Validator: Found {len(cities)} cities. Analyzing now...")
        all_results = []
        for city in cities:
            city_name = city.get('cityLabel', {}).get('value', 'N/A')
            print(f"  -> Analyzing {city_name}...")
            result = analyze_city_data(city, ai_model)
            all_results.append(result)
        
        print("\n--- Analysis Complete ---")
        print(json.dumps(all_results, indent=2))
        print_results_table(all_results)
    else:
        print("!!! FATAL: Could not retrieve city data.")
