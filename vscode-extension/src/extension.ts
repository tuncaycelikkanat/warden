import * as vscode from 'vscode';
import * as http from 'http';
import * as https from 'https';

let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;

const SUPPORTED_EXTENSIONS = ['.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.yaml', '.yml'];

export function activate(context: vscode.ExtensionContext) {
	diagnosticCollection = vscode.languages.createDiagnosticCollection('warden');
	context.subscriptions.push(diagnosticCollection);

	// Status Bar Item
	statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
	statusBarItem.command = 'warden.openDashboard';
	statusBarItem.text = '$(shield) WARDEN';
	statusBarItem.tooltip = 'WARDEN Governance Engine — Dashboardu Aç';
	statusBarItem.show();
	context.subscriptions.push(statusBarItem);

	const getConfig = () => {
		const cfg = vscode.workspace.getConfiguration('warden');
		return {
			serverUrl: cfg.get<string>('serverUrl', 'http://127.0.0.1:8000'),
			token: cfg.get<string>('apiToken', ''),
		};
	};

	const scanFile = (filePath: string, uri: vscode.Uri, isManual: boolean = false) => {
		const isSupported = SUPPORTED_EXTENSIONS.some(ext => filePath.toLowerCase().endsWith(ext));
		if (!isSupported) {
			if (isManual) {
				vscode.window.showWarningMessage(`Desteklenmeyen dosya türü. Desteklenenler: ${SUPPORTED_EXTENSIONS.join(', ')}`);
			}
			return;
		}

		if (isManual) {
			vscode.window.showInformationMessage(`WARDEN taraması başlatılıyor: ${filePath}`);
		}

		diagnosticCollection.delete(uri);

		const { serverUrl, token } = getConfig();
		const urlObj = new URL('/api/v1/scan', serverUrl);
		const isHttps = urlObj.protocol === 'https:';
		const client = isHttps ? https : http;

		const postData = JSON.stringify({ file_path: filePath });
		const headers: Record<string, string | number> = {
			'Content-Type': 'application/json',
			'Content-Length': Buffer.byteLength(postData),
		};
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}

		const req = client.request(
			{
				hostname: urlObj.hostname,
				port: urlObj.port || (isHttps ? 443 : 80),
				path: urlObj.pathname,
				method: 'POST',
				headers,
			},
			(res) => {
				let data = '';
				res.on('data', (chunk) => { data += chunk; });
				res.on('end', () => {
					try {
						const result = JSON.parse(data);
						if (isManual) {
							if (result.risk_level === 'high' || result.risk_level === 'critical') {
								vscode.window.showErrorMessage(`🚨 YÜKSEK RİSK: ${filePath} dosyasında güvenlik açığı bulundu!`);
							} else if (result.risk_level === 'medium') {
								vscode.window.showWarningMessage(`⚠️ ORTA RİSK: ${filePath} dosyasında uyarılar var.`);
							} else {
								vscode.window.showInformationMessage(`✅ GÜVENLİ: ${filePath} dosyası temiz.`);
							}
						}

						if (result.findings && Array.isArray(result.findings) && result.findings.length > 0) {
							const diagnostics: vscode.Diagnostic[] = [];
							for (const r of result.findings) {
								const line = (r.start && r.start.line) ? r.start.line - 1 : (r.line ? r.line - 1 : 0);
								const range = new vscode.Range(line, 0, line, 120);
								const message = `WARDEN: ${r.extra?.message || r.message || r.rule || 'Güvenlik veya Kalite Uyarısı'}`;
								const severity = (r.severity === 'ERROR' || r.severity === 'CRITICAL')
									? vscode.DiagnosticSeverity.Error
									: vscode.DiagnosticSeverity.Warning;

								diagnostics.push(new vscode.Diagnostic(range, message, severity));
							}
							diagnosticCollection.set(uri, diagnostics);
						}
					} catch (e) {
						if (isManual) {
							vscode.window.showErrorMessage('WARDEN API yanıtı çözümlenemedi.');
						}
					}
				});
			}
		);

		req.on('error', (e) => {
			if (isManual) {
				vscode.window.showErrorMessage(`WARDEN sunucusuna bağlanılamadı (${serverUrl}): ${e.message}`);
			}
		});

		req.write(postData);
		req.end();
	};

	// 1. Manuel Dosya Tarama Komutu
	const scanDisposable = vscode.commands.registerCommand('warden.scan', () => {
		const editor = vscode.window.activeTextEditor;
		if (!editor) {
			vscode.window.showErrorMessage('Lütfen taramak için bir dosya açın.');
			return;
		}
		scanFile(editor.document.uri.fsPath, editor.document.uri, true);
	});
	context.subscriptions.push(scanDisposable);

	// 2. Tam Kapsamlı Proje Denetim Komutu
	const auditDisposable = vscode.commands.registerCommand('warden.audit', () => {
		const workspaceFolders = vscode.workspace.workspaceFolders;
		if (!workspaceFolders) {
			vscode.window.showErrorMessage('Lütfen bir proje klasörü açın.');
			return;
		}
		const repoPath = workspaceFolders[0].uri.fsPath;
		vscode.window.showInformationMessage(`WARDEN Proje Denetimi başlatılıyor: ${repoPath}...`);

		const { serverUrl, token } = getConfig();
		const urlObj = new URL('/api/v1/scan', serverUrl);
		const isHttps = urlObj.protocol === 'https:';
		const client = isHttps ? https : http;

		const postData = JSON.stringify({ repo_path: repoPath });
		const headers: Record<string, string | number> = {
			'Content-Type': 'application/json',
			'Content-Length': Buffer.byteLength(postData),
		};
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}

		const req = client.request(
			{
				hostname: urlObj.hostname,
				port: urlObj.port || (isHttps ? 443 : 80),
				path: '/api/v1/dashboard/summary',
				method: 'GET',
				headers,
			},
			(res) => {
				let data = '';
				res.on('data', (chunk) => { data += chunk; });
				res.on('end', () => {
					try {
						const result = JSON.parse(data);
						const avg = result.average_score || '--';
						statusBarItem.text = `$(shield) WARDEN: ${avg}/100`;
						vscode.window.showInformationMessage(`✅ WARDEN: Ortalama Puan ${avg}/100. Dashboard'dan inceleyebilirsiniz.`);
					} catch {
						// Safe ignore
					}
				});
			}
		);

		req.on('error', (e) => {
			vscode.window.showErrorMessage(`WARDEN bağlantı hatası: ${e.message}`);
		});
		req.end();
	});
	context.subscriptions.push(auditDisposable);

	// 3. Web Dashboard'u Aç Komutu
	const dashboardDisposable = vscode.commands.registerCommand('warden.openDashboard', () => {
		const { serverUrl } = getConfig();
		const dashboardUrl = `${serverUrl.replace(/\/$/, '')}/dashboard/`;
		vscode.env.openExternal(vscode.Uri.parse(dashboardUrl));
	});
	context.subscriptions.push(dashboardDisposable);

	// 4. Kaydetmede Otomatik Tarama
	const saveDisposable = vscode.workspace.onDidSaveTextDocument((document) => {
		scanFile(document.uri.fsPath, document.uri, false);
	});
	context.subscriptions.push(saveDisposable);
}

export function deactivate() {
	if (statusBarItem) {
		statusBarItem.dispose();
	}
}
