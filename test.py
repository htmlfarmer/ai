import ollama

config = ''

stream = ollama.chat(
    model='llama3.2:latest',
    messages=[
       {'role': 'system', 'content': config},
       {'role': 'user', 'content': 'Write me a poem about me the author'},
    ],
   stream=True,
   options={
                "temperature": 2.0,
                "top_p": 0.9
            }
 )

for chunk in stream:
   print(chunk['message'].get('content', ''), end='', flush=True)