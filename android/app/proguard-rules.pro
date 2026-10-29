# Le pont JavaScript et Chaquopy ne doivent pas être obfusqués.
-keepclassmembers class dev.pyide.mobile.PyBridge { public *; }
-keep class com.chaquo.python.** { *; }
