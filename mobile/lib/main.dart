import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'screens/chat_screen.dart';
import 'screens/worker_screen.dart';
import 'services/discovery_service.dart';
import 'services/inference_service.dart';
import 'services/worker_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await WorkerService.initBackgroundService();
  runApp(const LlmClusterApp());
}

class LlmClusterApp extends StatelessWidget {
  const LlmClusterApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => DiscoveryService()..startBrowsing()),
        ChangeNotifierProxyProvider<DiscoveryService, WorkerService>(
          create: (ctx) => WorkerService(ctx.read<DiscoveryService>()),
          update: (_, discovery, prev) => prev ?? WorkerService(discovery),
        ),
        ChangeNotifierProxyProvider<DiscoveryService, InferenceService>(
          create: (ctx) => InferenceService(ctx.read<DiscoveryService>()),
          update: (_, discovery, prev) => prev ?? InferenceService(discovery),
        ),
      ],
      child: MaterialApp(
        title: 'LLM Cluster',
        theme: ThemeData(
          colorSchemeSeed: const Color(0xFF1a73e8),
          useMaterial3: true,
        ),
        darkTheme: ThemeData(
          colorSchemeSeed: const Color(0xFF1a73e8),
          brightness: Brightness.dark,
          useMaterial3: true,
        ),
        home: const _RootNav(),
      ),
    );
  }
}

class _RootNav extends StatefulWidget {
  const _RootNav();

  @override
  State<_RootNav> createState() => _RootNavState();
}

class _RootNavState extends State<_RootNav> {
  int _index = 0;

  static const _screens = [
    ChatScreen(),
    WorkerScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final worker = context.watch<WorkerService>();

    return Scaffold(
      body: _screens[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.chat_outlined),
            selectedIcon: Icon(Icons.chat),
            label: 'Chat',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: worker.running,
              child: const Icon(Icons.hub_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: worker.running,
              label: const Text('●'),
              child: const Icon(Icons.hub),
            ),
            label: 'Worker',
          ),
        ],
      ),
    );
  }
}
