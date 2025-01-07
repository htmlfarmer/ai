import ollama
import serial
import time

# Arduino serial configuration
arduino_port = '/dev/ttyACM0'  # Replace with 'COMx' on Windows or '/dev/ttyUSBx' on Linux
baud_rate = 9600

# Initialize the serial connection
ser = serial.Serial(arduino_port, baud_rate, timeout=1)
time.sleep(2)  # Allow time for the Arduino to reset

# Ollama configuration
config = ''

# Stream chat response from Ollama
stream = ollama.chat(
    model='llama3.2:latest',
    messages=[
       {'role': 'system', 'content': config},
       {'role': 'user', 'content': 'what is the meaning of life?'},
    ],
    stream=True,
    options={
        "temperature": 2.0,
        "top_p": 0.9
    }
)

# Send Ollama response to Arduino
for chunk in stream:
    message = chunk['message'].get('content', '')
    if message:
        print(message, end='', flush=True)  # Print for local debugging
        if ser.is_open:
            # Send message in chunks of 16 characters (fits on 16x2 LCD display)
            for i in range(0, len(message), 16):
                ser.write((message[i:i+16] + '\n').encode('utf-8'))
                time.sleep(1)  # Delay to ensure Arduino processes the data
