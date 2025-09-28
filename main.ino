// FILENAME: ai_terminal.ino (Version with Serial Debugging)

#include "LedControl.h"
#include "LiquidCrystal.h"
#include "font.h" 

// --- Pin Definitions (Your Original, Unchanged Pins) ---
const int latchPin_7Segment = 24, clockPin_7Segment = 26, dataPin_7Segment = 22;
const int dataInPin_Matrix = 12, loadCsPin_Matrix = 11, clockPin_Matrix = 10;
const int rsPin_LCD = 9, enablePin_LCD = 8, d4Pin_LCD = 2, d5Pin_LCD = 3, d6Pin_LCD = 4, d7Pin_LCD = 5;
const int ledPin_Indicator = 13, pirPin_Sensor = 7;

// --- All other global variables are unchanged ---
unsigned char sevenSegmentTable[] = {0x3f,0x06,0x5b,0x4f,0x66,0x6d,0x7d,0x07,0x7f,0x6f,0x77,0x7c,0x39,0x5e,0x79,0x71,0x00};
volatile int pirMotionCount = 0;
LedControl lc = LedControl(dataInPin_Matrix, clockPin_Matrix, loadCsPin_Matrix, 1);
unsigned long lastMatrixScrollTime = 0;
const int matrixScrollInterval = 80; 
int matrixTextPos = 0;
int matrixCol = 0;
byte matrixBuffer[8] = {0};
LiquidCrystal lcd(rsPin_LCD, enablePin_LCD, d4Pin_LCD, d5Pin_LCD, d6Pin_LCD, d7Pin_LCD);
String userQuestion = "Ask Gemma AI...";
String gemmaAnswer = "Awaiting Guidance...";
unsigned long lastLcdScroll = 0;
const int lcdScrollInterval = 350; 
int questionScrollPos = 0;
int answerScrollPos = 0;
int pirValue;
unsigned long lastPirPoll = 0;
const unsigned long pirPollInterval = 50;
bool pirActiveHigh = true;
int lastPirState = 0;
char messageBuffer[256];
int serialIdx = 0;
bool messageReady = false;

void setup() {
  Serial.begin (9600);
  pinMode(latchPin_7Segment, OUTPUT);
  pinMode(clockPin_7Segment, OUTPUT);
  pinMode(dataPin_7Segment, OUTPUT);
  lc.shutdown(0, false);
  lc.setIntensity(0, 5);
  lc.clearDisplay(0);
  pinMode(ledPin_Indicator, OUTPUT);
  pinMode(pirPin_Sensor, INPUT);
  digitalWrite(ledPin_Indicator, LOW);
  lcd.begin(16, 2);
  updateLCD();
  Serial.println(F("--- AI Terminal Ready ---"));
}

void loop() {
  pollPIRIfNeeded();
  processSerial();
  updateLCD();
  displayOn7Segment(pirMotionCount % 10);
  updateMatrixScroll();
}

// All other functions (displayOn7Segment, checkPIR, etc.) are unchanged

void processSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      messageBuffer[serialIdx] = '\0';
      messageReady = true;
      serialIdx = 0;
    } else {
      if (serialIdx < sizeof(messageBuffer) - 1) messageBuffer[serialIdx++] = c;
    }
  }

  if (messageReady) {
    // --- NEW DEBUGGING CODE ---
    // Print the raw message the moment it's fully received.
    Serial.println("------------------------------------");
    Serial.print("Arduino received raw message: [");
    Serial.print(messageBuffer);
    Serial.println("]");
    // --- END NEW DEBUGGING CODE ---

    if (strncmp(messageBuffer, "USER:", 5) == 0) {
      userQuestion = String(messageBuffer + 5);
      questionScrollPos = 0;
      
      // --- NEW DEBUGGING CODE ---
      Serial.println(">>> Parsed as USER message.");
      Serial.print(">>> Updated userQuestion to: ");
      Serial.println(userQuestion);
      // --- END NEW DEBUGGING CODE ---
      
    } else if (strncmp(messageBuffer, "GEMMA:", 6) == 0) {
      gemmaAnswer = String(messageBuffer + 6);
      answerScrollPos = 0;
      matrixTextPos = 0;
      matrixCol = 0;
      
      // --- NEW DEBUGGING CODE ---
      Serial.println(">>> Parsed as GEMMA message.");
      Serial.print(">>> Updated gemmaAnswer to: ");
      Serial.println(gemmaAnswer);
      // --- END NEW DEBUGGING CODE ---
    }
    messageReady = false;
  }
}

// ... the rest of the functions (updateLCD, updateMatrixScroll, etc.) are exactly the same ...
void displayOn7Segment(unsigned char num) { digitalWrite(latchPin_7Segment, LOW); shiftOut(dataPin_7Segment, clockPin_7Segment, MSBFIRST, sevenSegmentTable[num]); digitalWrite(latchPin_7Segment, HIGH); }
void checkPIR() { int raw = digitalRead(pirPin_Sensor); int newVal = pirActiveHigh ? raw : !raw; if (newVal && !lastPirState) { pirMotionCount++; } lastPirState = newVal; pirValue = newVal; digitalWrite(ledPin_Indicator, pirValue); }
void pollPIRIfNeeded() { unsigned long now = millis(); if (now - lastPirPoll >= pirPollInterval) { lastPirPoll = now; checkPIR(); } }
void updateLCD() { unsigned long now = millis(); if (now - lastLcdScroll < lcdScrollInterval) return; lastLcdScroll = now; lcd.setCursor(0, 0); String qPadded = " " + userQuestion + " "; if (qPadded.length() <= 16) qPadded = userQuestion; String qSub = qPadded.substring(questionScrollPos, questionScrollPos + 16); lcd.print(qSub); for (int i = qSub.length(); i < 16; i++) lcd.print(' '); questionScrollPos++; if (questionScrollPos > (qPadded.length() - 16)) questionScrollPos = 0; lcd.setCursor(0, 1); String aPadded = " " + gemmaAnswer + " "; if (aPadded.length() <= 16) aPadded = gemmaAnswer; String aSub = aPadded.substring(answerScrollPos, answerScrollPos + 16); lcd.print(aSub); for (int i = aSub.length(); i < 16; i++) lcd.print(' '); answerScrollPos++; if (answerScrollPos > (aPadded.length() - 16)) answerScrollPos = 0; }
void updateMatrixScroll() { unsigned long now = millis(); if (now - lastMatrixScrollTime < matrixScrollInterval) return; lastMatrixScrollTime = now; for (int i = 0; i < 7; i++) { matrixBuffer[i] = matrixBuffer[i + 1]; } char currentChar = gemmaAnswer[matrixTextPos]; int fontIndex = currentChar - 32; if (fontIndex < 0 || fontIndex >= FONT_LENGTH) fontIndex = 0; matrixBuffer[7] = pgm_read_byte(&(font[fontIndex][matrixCol])); for (int i = 0; i < 8; i++) { lc.setRow(0, i, matrixBuffer[i]); } matrixCol++; if (matrixCol >= 8) { matrixCol = 0; matrixTextPos++; if (matrixTextPos >= gemmaAnswer.length()) { matrixTextPos = 0; } } }
