#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#undef BLACK          // Fix FastLED conflict
#include <FastLED.h>

// --------- PINS ----------
#define SOIL_PIN 1
#define LDR_PIN  4

#define SDA_PIN 8
#define SCL_PIN 9

#define LED_PIN  10      // LED STRIP DATA PIN
#define NUM_LEDS 15

// -------- OLED ----------
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDR 0x3C

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// -------- LED STRIP -----
CRGB leds[NUM_LEDS];

// -------- STATE ---------
int lastSoil  = -1;
int lastLight = -1;

// -------- SETUP ---------
void setup() {
  Serial.begin(921600);
  delay(300);

  Wire.begin(SDA_PIN, SCL_PIN);

  // OLED INIT
  if(!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)){
    while(true); // OLED fail-safe
  }

  display.clearDisplay();
  display.setTextSize(1.25);
  display.setTextColor(SSD1306_WHITE);

  // LED STRIP INIT
  FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS);
  FastLED.clear();
  FastLED.show();
}

// -------- WARM LED -------
void setWarm(bool on){
  if(on){
    for(int i=0;i<NUM_LEDS;i++){
      leds[i] = CRGB(255, 120, 50);  // 🌱 warm greenhouse light
    }
  } else {
    for(int i=0;i<NUM_LEDS;i++){
      leds[i] = CRGB::Black;
    }
  }
  FastLED.show();
}

// -------- LOOP ----------
void loop() {

  int soil  = analogRead(SOIL_PIN);
  int light = analogRead(LDR_PIN);

  // -------- STATUS --------
  String dayStatus  = (light >= 4000) ? "Night" : "Day";
  String soilStatus = (soil > 2500) ? "OK" : "DRY";

  // -------- OLED --------
  display.clearDisplay();
  display.setCursor(0,0);
  display.println("PLANT DISPLAY");
  display.println("----------------");
  display.print("Soil: ");  display.println(soil);
 display.print("Soil: ");  display.println(soilStatus);
  display.print("Light: "); display.println(light);
  display.print("Mode: ");  display.println(dayStatus);
  display.display();

  // -------- SERIAL (ONLY IF CHANGE) --------
  if (abs(soil - lastSoil) > 15 || abs(light - lastLight) > 15) {
    Serial.print(soil);
    Serial.print(",");
    Serial.println(light);

    lastSoil  = soil;
    lastLight = light;
  }

  // -------- RECEIVE COMMANDS --------
  while(Serial.available()){
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if(cmd == "LED_ON"){
      setWarm(true);
    }
    else if(cmd == "LED_OFF"){
      setWarm(false);
    }
  }

  delay(15);   // ultra-low latency, stable serial
}
