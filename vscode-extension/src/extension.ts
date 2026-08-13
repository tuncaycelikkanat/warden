import * as vscode from 'vscode';
import * as http from 'http';

export function activate(context: vscode.ExtensionContext) {
	const disposable = vscode.commands.registerCommand('warden.scan', () => {
		const editor = vscode.window.activeTextEditor;
		if (!editor) {
			vscode.window.showErrorMessage('Lütfen taramak için bir dosya açın.');
			return;
		}

		const filePath = editor.document.uri.fsPath;
		if (!filePath.endsWith('.py')) {
			vscode.window.showWarningMessage('Şu an sadece Python (.py) dosyaları destekleniyor.');
			return;
		}

		vscode.window.showInformationMessage(`Warden taraması başlatılıyor: ${filePath}`);

		const postData = JSON.stringify({ file_path: filePath });

		const options = {
			hostname: 'localhost',
			port: 8000,
			path: '/api/v1/scan',
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Content-Length': Buffer.byteLength(postData)
			}
		};

		const req = http.request(options, (res) => {
			let data = '';

			res.on('data', (chunk) => {
				data += chunk;
			});

			res.on('end', () => {
				try {
					const result = JSON.parse(data);
					if (result.risk_level === 'high') {
						vscode.window.showErrorMessage(`🚨 YÜKSEK RİSK: ${filePath} dosyasında güvenlik açığı bulundu!`);
					} else if (result.risk_level === 'medium') {
						vscode.window.showWarningMessage(`⚠️ ORTA RİSK: ${filePath} dosyasında uyarılar var.`);
					} else {
						vscode.window.showInformationMessage(`✅ GÜVENLİ: ${filePath} dosyası temiz.`);
					}
				} catch (e) {
					vscode.window.showErrorMessage('Warden API yanıtı okunamadı.');
				}
			});
		});

		req.on('error', (e) => {
			vscode.window.showErrorMessage(`Warden sunucusuna bağlanılamadı: ${e.message}. Sunucunun (localhost:8000) çalıştığından emin olun.`);
		});

		req.write(postData);
		req.end();
	});

	context.subscriptions.push(disposable);
}

export function deactivate() {}
