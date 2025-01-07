#include <LiquidCrystal.h>

// Initialize the library with the pins connected to the LCD
LiquidCrystal lcd(7, 8, 9, 10, 11, 12);

void setup() {
  lcd.begin(16, 2); // Set up the LCD's number of columns and rows
  Serial.begin(9600); // Initialize serial communication
  lcd.print("Waiting for"); 
  lcd.setCursor(0, 1);
  lcd.print("data...");
}

void loop() {
  // Check if data is available on the serial port
  if (Serial.available() > 0) {
    lcd.clear(); // Clear the display for new data
    String data = Serial.readStringUntil('\n'); // Read a line of input
    lcd.setCursor(0, 0); // Start on the first row
    lcd.print(data.substring(0, 16)); // Print first 16 characters
    if (data.length() > 16) {
      lcd.setCursor(0, 1); // Move to the second row
      lcd.print(data.substring(16, 32)); // Print next 16 characters
    }
  }
}
