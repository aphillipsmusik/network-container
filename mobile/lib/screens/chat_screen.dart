import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:provider/provider.dart';
import '../models/cluster_node.dart';
import '../services/discovery_service.dart';
import '../services/inference_service.dart';

class _Message {
  final String role;
  String content;
  bool streaming;
  _Message(this.role, this.content, {this.streaming = false});
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _messages = <_Message>[];
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  bool _initialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialized) {
      _initialized = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => _init());
    }
  }

  Future<void> _init() async {
    final inference = context.read<InferenceService>();
    await inference.selectBestNode();
  }

  @override
  Widget build(BuildContext context) {
    final inference = context.watch<InferenceService>();
    final discovery = context.watch<DiscoveryService>();
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(28),
          child: _SourceBanner(inference: inference, discovery: discovery),
        ),
      ),
      body: Column(
        children: [
          // ── Messages ───────────────────────────────────────────────────
          Expanded(
            child: _messages.isEmpty
                ? _EmptyState(inference: inference)
                : ListView.builder(
                    controller: _scrollCtrl,
                    padding: const EdgeInsets.all(12),
                    itemCount: _messages.length,
                    itemBuilder: (_, i) => _MessageBubble(
                      message: _messages[i],
                    ),
                  ),
          ),

          // ── Input bar ──────────────────────────────────────────────────
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
              child: Row(children: [
                Expanded(
                  child: TextField(
                    controller: _inputCtrl,
                    enabled: !inference.generating,
                    maxLines: 4,
                    minLines: 1,
                    textInputAction: TextInputAction.newline,
                    decoration: InputDecoration(
                      hintText: 'Message…',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(24),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 10),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                inference.generating
                    ? IconButton(
                        icon: const Icon(Icons.stop_circle_outlined),
                        onPressed: () {/* TODO: cancel stream */},
                        color: theme.colorScheme.error,
                      )
                    : IconButton.filled(
                        icon: const Icon(Icons.send),
                        onPressed: _send,
                      ),
              ]),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty) return;

    _inputCtrl.clear();

    setState(() {
      _messages.add(_Message('user', text));
      _messages.add(_Message('assistant', '', streaming: true));
    });
    _scrollToBottom();

    final history = _messages
        .where((m) => !m.streaming || m.content.isNotEmpty)
        .map((m) => {'role': m.role, 'content': m.content})
        .toList();

    final inference = context.read<InferenceService>();
    await for (final token in inference.chatStream(history)) {
      setState(() {
        _messages.last.content += token;
      });
      _scrollToBottom();
    }

    setState(() => _messages.last.streaming = false);
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }
}

// ── Widgets ───────────────────────────────────────────────────────────────────

class _SourceBanner extends StatelessWidget {
  final InferenceService inference;
  final DiscoveryService discovery;

  const _SourceBanner(
      {required this.inference, required this.discovery});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = inference.usingOnDevice
        ? Colors.orange
        : theme.colorScheme.primaryContainer;

    return Container(
      width: double.infinity,
      color: color,
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 16),
      child: Row(children: [
        Icon(
          inference.usingOnDevice ? Icons.phone_iphone : Icons.cloud_done,
          size: 14,
          color: theme.colorScheme.onPrimaryContainer,
        ),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            inference.sourceLabel,
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.colorScheme.onPrimaryContainer),
            overflow: TextOverflow.ellipsis,
          ),
        ),
        // Node picker
        if (discovery.inferenceNodes.isNotEmpty)
          GestureDetector(
            onTap: () => _showNodePicker(context),
            child: Text(
              'Switch',
              style: theme.textTheme.labelSmall?.copyWith(
                decoration: TextDecoration.underline,
                color: theme.colorScheme.onPrimaryContainer,
              ),
            ),
          ),
      ]),
    );
  }

  void _showNodePicker(BuildContext context) {
    final inference = context.read<InferenceService>();
    showModalBottomSheet(
      context: context,
      builder: (_) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.phone_android),
            title: const Text('On-device model'),
            subtitle: const Text('Slower, works offline'),
            onTap: () {
              inference.useOnDevice();
              Navigator.pop(context);
            },
          ),
          const Divider(),
          ...discovery.inferenceNodes.map((node) => ListTile(
                leading: const Icon(Icons.hub),
                title: Text(node.name),
                subtitle: Text('${node.inferenceBaseUrl}'
                    '${node.ramGb != null ? " · ${node.ramGb}GB" : ""}'),
                onTap: () {
                  inference.useNode(node);
                  Navigator.pop(context);
                },
              )),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final _Message message;
  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final theme = Theme.of(context);

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.82),
        decoration: BoxDecoration(
          color: isUser
              ? theme.colorScheme.primary
              : theme.colorScheme.surfaceVariant,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(18),
            topRight: const Radius.circular(18),
            bottomLeft: Radius.circular(isUser ? 18 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 18),
          ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: message.role == 'assistant'
            ? MarkdownBody(
                data: message.content.isEmpty && message.streaming
                    ? '▌'
                    : message.content,
                styleSheet: MarkdownStyleSheet(
                  p: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                ),
              )
            : Text(
                message.content,
                style: TextStyle(color: theme.colorScheme.onPrimary),
              ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final InferenceService inference;
  const _EmptyState({required this.inference});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.chat_bubble_outline,
                size: 56,
                color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 16),
            Text(
              inference.usingOnDevice
                  ? 'On-device mode\nNo cluster detected on this network.'
                  : 'Connected to cluster\nStart a conversation below.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.outline,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}
