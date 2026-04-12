import 'dart:io';
import 'package:flutter/material.dart';
import 'package:network_info_plus/network_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/worker_service.dart';
import '../services/discovery_service.dart';

class WorkerScreen extends StatefulWidget {
  const WorkerScreen({super.key});

  @override
  State<WorkerScreen> createState() => _WorkerScreenState();
}

class _WorkerScreenState extends State<WorkerScreen> {
  final _nameCtrl = TextEditingController();
  int _rpcPort = 50052;
  int _gpuLayers = 0;
  String _myIp = '…';

  @override
  void initState() {
    super.initState();
    _loadPrefs();
    _detectIp();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _nameCtrl.text = prefs.getString('node_name') ??
          '${Platform.isAndroid ? "android" : "ios"}-${Platform.localHostname.split('.').first}';
      _rpcPort = prefs.getInt('rpc_port') ?? 50052;
      _gpuLayers = prefs.getInt('gpu_layers') ?? 0;
    });
  }

  Future<void> _savePrefs() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('node_name', _nameCtrl.text);
    await prefs.setInt('rpc_port', _rpcPort);
    await prefs.setInt('gpu_layers', _gpuLayers);
  }

  Future<void> _detectIp() async {
    try {
      final ip = await NetworkInfo().getWifiIP();
      setState(() => _myIp = ip ?? 'Not on WiFi');
    } catch (_) {
      setState(() => _myIp = 'Unknown');
    }
  }

  @override
  Widget build(BuildContext context) {
    final worker = context.watch<WorkerService>();
    final discovery = context.watch<DiscoveryService>();
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Worker Node'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _detectIp,
            tooltip: 'Refresh IP',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Status card ───────────────────────────────────────────────
          Card(
            color: worker.running
                ? theme.colorScheme.primaryContainer
                : theme.colorScheme.surfaceVariant,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Icon(
                      worker.running ? Icons.circle : Icons.circle_outlined,
                      color: worker.running ? Colors.green : Colors.grey,
                      size: 14,
                    ),
                    const SizedBox(width: 8),
                    Text(worker.status,
                        style: theme.textTheme.titleMedium),
                  ]),
                  if (worker.running) ...[
                    const SizedBox(height: 8),
                    Text('Uptime: ${_fmtUptime(worker.uptimeSeconds)}',
                        style: theme.textTheme.bodySmall),
                    Text('IP: $_myIp:$_rpcPort',
                        style: theme.textTheme.bodySmall),
                    Text('Peers: ${discovery.nodes.length} node(s) on network',
                        style: theme.textTheme.bodySmall),
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // ── Configuration ─────────────────────────────────────────────
          Text('Configuration', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),

          TextField(
            controller: _nameCtrl,
            enabled: !worker.running,
            decoration: const InputDecoration(
              labelText: 'Node name',
              hintText: 'e.g. android-pixel8',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),

          Row(children: [
            Expanded(
              child: TextField(
                enabled: !worker.running,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'RPC port',
                  border: OutlineInputBorder(),
                ),
                controller: TextEditingController(text: '$_rpcPort'),
                onChanged: (v) => _rpcPort = int.tryParse(v) ?? 50052,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                enabled: !worker.running,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'GPU layers (0=CPU)',
                  border: OutlineInputBorder(),
                ),
                controller: TextEditingController(text: '$_gpuLayers'),
                onChanged: (v) => _gpuLayers = int.tryParse(v) ?? 0,
              ),
            ),
          ]),

          const SizedBox(height: 8),
          Text(
            'Your IP on this network: $_myIp',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.outline),
          ),

          if (_myIp == 'Not on WiFi')
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '⚠  Connect to WiFi for cluster participation. '
                'Cellular is too slow for inter-node activation transfer.',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: Colors.orange),
              ),
            ),

          const SizedBox(height: 20),

          // ── Start / stop ──────────────────────────────────────────────
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: worker.running
                  ? () => worker.stop()
                  : () async {
                      await _savePrefs();
                      final ram = (await _getRamGb());
                      if (mounted) {
                        await worker.start(
                          nodeName: _nameCtrl.text,
                          rpcPort: _rpcPort,
                          gpuLayers: _gpuLayers,
                          ramGb: ram,
                        );
                      }
                    },
              icon: Icon(worker.running ? Icons.stop : Icons.play_arrow),
              label: Text(worker.running ? 'Stop Worker' : 'Start Worker'),
              style: worker.running
                  ? FilledButton.styleFrom(
                      backgroundColor: theme.colorScheme.error)
                  : null,
            ),
          ),

          const SizedBox(height: 24),

          // ── Discovered peers ──────────────────────────────────────────
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Cluster Nodes (${discovery.nodes.length})',
                  style: theme.textTheme.titleSmall),
              TextButton(
                onPressed: () {},
                child: const Text('Refresh'),
              ),
            ],
          ),

          if (discovery.nodes.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Text(
                'No nodes discovered yet.\nStart the worker to join the cluster.',
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.outline),
                textAlign: TextAlign.center,
              ),
            ),

          ...discovery.nodes.map((node) => ListTile(
                leading: Icon(
                  node.platform == 'android'
                      ? Icons.phone_android
                      : node.platform == 'ios'
                          ? Icons.phone_iphone
                          : Icons.computer,
                  color: theme.colorScheme.primary,
                ),
                title: Text(node.name),
                subtitle: Text(
                  '${node.rpcEndpoint}'
                  '${node.ramGb != null ? "  ·  ${node.ramGb}GB RAM" : ""}'
                  '${node.fullNode ? "  ·  full-node" : ""}',
                ),
                trailing: node.fullNode
                    ? Chip(
                        label: const Text('API'),
                        backgroundColor:
                            theme.colorScheme.secondaryContainer,
                        padding: EdgeInsets.zero,
                        labelStyle: theme.textTheme.labelSmall,
                      )
                    : null,
              )),
        ],
      ),
    );
  }

  String _fmtUptime(int s) {
    if (s < 60) return '${s}s';
    if (s < 3600) return '${s ~/ 60}m ${s % 60}s';
    return '${s ~/ 3600}h ${(s % 3600) ~/ 60}m';
  }

  Future<double> _getRamGb() async {
    // In production: use platform channel to get real RAM
    // ProcessInfo.maxRss on iOS, ActivityManager on Android
    return Platform.isAndroid ? 8.0 : 6.0;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    super.dispose();
  }
}
