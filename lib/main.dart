import 'package:flutter/material.dart';
import 'screens/main_store_page.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TECH-GEAR PCSTORE',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        scaffoldBackgroundColor: const Color(0xFF0D0D12),
        appBarTheme: const AppBarTheme(backgroundColor: Color(0xFF0D0D12), elevation: 0),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF2F80FF),
          secondary: Color(0xFFFF2D78),
          surface: Colors.white,
          onSurface: Colors.black,
        ),
        useMaterial3: true,
      ),
      home: const MainStorePage(),
    );
  }
}