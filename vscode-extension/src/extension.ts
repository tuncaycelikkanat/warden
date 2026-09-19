import * as vscode from 'vscode';
import * as http from 'http';

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {
	diagnosticCollection = vscode.languages.createDiagnosticCollection('warden');
	context.subscriptions.push(diagnosticCollection);

	const scanFile = (filePath: string, uri: vscode.Uri, isManual: boolean = false) => {
		if (!filePath.endsWith('.py')) {
			if (isManual) {
				vscode.window.showWarningMessage('Şu an sadece Python (.py) dosyaları destekleniyor.');
			}
			return;
		}

		if (isManual) {
			vscode.window.showInformationMessage(`Warden taraması başlatılıyor: ${filePath}`);
		} else {
			console.log(`Otomatik Warden taraması tetiklendi: ${filePath}`);
		}
		
		diagnosticCollection.delete(uri); // Eski çizgileri temizle o dosya için

		const postData = JSON.stringify({ file_path: filePath });

		const options = {
			hostname: '127.0.0.1',
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
			res.on('data', (chunk) => { data += chunk; });
			res.on('end', () => {
				try {
					const result = JSON.parse(data);
					
					if (isManual) {
						if (result.risk_level === 'high') {
							vscode.window.showErrorMessage(`🚨 YÜKSEK RİSK: ${filePath} dosyasında güvenlik açığı bulundu!`);
						} else if (result.risk_level === 'medium') {
							vscode.window.showWarningMessage(`⚠️ ORTA RİSK: ${filePath} dosyasında uyarılar var.`);
						} else {
							vscode.window.showInformationMessage(`✅ GÜVENLİ: ${filePath} dosyası temiz.`);
						}
					}

					// Hatalı satırların altını çizme (Diagnostics)
					if (result.findings && Array.isArray(result.findings)) {
						if (result.findings.length > 0) {
							const diagnostics: vscode.Diagnostic[] = [];
							
							for (const r of result.findings) {
								const line = (r.start && r.start.line) ? r.start.line - 1 : 0;
								const range = new vscode.Range(line, 0, line, 100);
								const message = `WARDEN: ${r.extra?.message || 'Güvenlik Açığı'}`;
								
								const diagnostic = new vscode.Diagnostic(
									range,
									message,
									vscode.DiagnosticSeverity.Error
								);
								diagnostics.push(diagnostic);
							}
							
							diagnosticCollection.set(uri, diagnostics);
						}
					}
				} catch (e) {
					console.error('Warden API yanıtı okunamadı.', e);
					if (isManual) {
						vscode.window.showErrorMessage('Warden API yanıtı okunamadı veya sunucudan hata döndü.');
					}
				}
			});
		});

		req.on('error', (e) => {
			if (isManual) {
				vscode.window.showErrorMessage(`Warden sunucusuna bağlanılamadı: ${e.message}. Sunucunun (localhost:8000) çalıştığından emin olun.`);
			}
			console.error(`Warden sunucusuna bağlanılamadı: ${e.message}`);
		});

		req.write(postData);
		req.end();
	};

	// 1. Manuel Komut
	const disposable = vscode.commands.registerCommand('warden.scan', () => {
		const editor = vscode.window.activeTextEditor;
		if (!editor) {
			vscode.window.showErrorMessage('Lütfen taramak için bir dosya açın.');
			return;
		}
		scanFile(editor.document.uri.fsPath, editor.document.uri, true);
	});
	context.subscriptions.push(disposable);

	const auditDisposable = vscode.commands.registerCommand('warden.audit', () => {
		const workspaceFolders = vscode.workspace.workspaceFolders;
		if (!workspaceFolders) {
			vscode.window.showErrorMessage('Lütfen bir proje klasörü açın.');
			return;
		}
		const repoPath = workspaceFolders[0].uri.fsPath;
		vscode.window.showInformationMessage(`WARDEN Full Audit başlatılıyor: ${repoPath}... Lütfen bekleyin.`);

		const postData = JSON.stringify({ repo_path: repoPath });
		const options = {
			hostname: '127.0.0.1',
			port: 8000,
			path: '/api/v1/audit',
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Content-Length': Buffer.byteLength(postData)
			}
		};

		const req = http.request(options, (res) => {
			let data = '';
			res.on('data', (chunk) => { data += chunk; });
			res.on('end', () => {
				try {
					const result = JSON.parse(data);
					if (result.status === 'success') {
						const score = result.scorecard.total_score;
						const grade = result.scorecard.grade;
						vscode.window.showInformationMessage(`✅ WARDEN Audit Tamamlandı! Puan: ${score}/100 (Not: ${grade}). Rapor: ${result.md_path}`);
						// Open the markdown file
						vscode.workspace.openTextDocument(result.md_path).then(doc => {
							vscode.window.showTextDocument(doc);
						});
					} else {
						vscode.window.showErrorMessage(`Audit başarısız oldu.`);
					}
				} catch (e) {
					console.error('Audit yanıtı okunamadı.', e);
					vscode.window.showErrorMessage('Warden API Audit yanıtı okunamadı.');
				}
			});
		});

		req.on('error', (e) => {
			vscode.window.showErrorMessage(`Warden sunucusuna bağlanılamadı: ${e.message}`);
		});

		req.write(postData);
		req.end();
	});
	context.subscriptions.push(auditDisposable);

	// 2. Otomatik Kaydetme Olayı (Adım 4.4 & 4.5)
	const saveDisposable = vscode.workspace.onDidSaveTextDocument((document) => {
		console.log(`Dosya kaydedildi, taranıyor: ${document.uri.fsPath}`);
		scanFile(document.uri.fsPath, document.uri, false);
	});
	context.subscriptions.push(saveDisposable);
}

export function deactivate() {}
