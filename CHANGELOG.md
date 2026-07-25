# Changelog

## 4.3.0 — Personal Control

### Experiência

- Painel inicial personalizável e persistente para Trabalho, Estudo e Pessoal.
- Modo foco, largura de leitura, espaçamento, código, alto contraste e fontes
  alternativas sem alterar a identidade monocromática.
- Linha do tempo operacional dentro das respostas e comparação A/B com diff,
  duração, tokens, custo estimado e TTFT somente quando realmente medido.
- Capas monocromáticas determinísticas para projetos.

### Sistemas

- Central de conexões, Model Lab, workflows versionados, modo de ensaio,
  verificador de respostas, saúde, avaliações pessoais e governança de agentes.
- Reindexação incremental, versões, duplicatas e índice semântico local
  opcional na biblioteca.
- Backup completo do usuário, opcionalmente criptografado e sempre sem
  credenciais.
- Verificação Ed25519/SHA-256 de atualizações, canais Estável/Testes, snapshots
  íntegros e reversão transacional. Instalação automática continua desativada.

### Confiança

- Políticas globais e por projeto, suspensão emergencial e perfil 100% local.
- Cofre v2 com concessões permanentes, de sessão, temporárias e bloqueadas.
- OAuth Gmail/Calendar em memória, segredos removidos de subprocessos e
  revogação sem fallback para arquivos ou `.env` no desktop protegido.
- Auditoria investigável com cadeia SHA-256 interna e relatórios redigidos.
- Simulações convertem segredos em variáveis antes de persistir e são
  invalidadas quando um arquivo afetado muda.
- Especialistas incompletos ficam indisponíveis; avaliações futuras precisam
  demonstrar função única, contratos e ganho mensurável.

## 4.2.0 — Monochrome Trust

### Identidade e experiência

- Nova direção visual estritamente preta, branca e cinza, baseada no conceito
  aprovado pelo usuário.
- Wordmark original Aether aplicada na sidebar, onboarding, configurações e
  splash; o “A” recortado da mesma arte virou avatar compacto do assistente.
- Sidebar escura, área principal clara, topo editorial, projeto ativo visível,
  página inicial mais limpa e painel contextual reorganizado.
- Ícones de aplicativo, instalador e bandeja refeitos para leitura correta em
  tamanhos pequenos e fundos claros ou escuros.
- Posição, tamanho e maximização da janela são restaurados com validação de
  monitor; progresso real pode ser refletido na barra do sistema.

### Controle e transparência

- Modo de proteção global persistente: `normal`, `confirm_all` e `read_only`.
- Classificação fail-closed para ações desconhecidas nos modos restritivos.
- O limite global é aplicado a chat, rotas diretas, aprovação, repetição e
  automações sem permitir que uma regra de sessão o contorne.
- Inspetor de contexto sem efeitos colaterais, com histórico, memória,
  documentos, skills, anexos, estimativa local de tokens e mapa de privacidade.
- Exportação redigida da auditoria em JSON, com operações, eventos, filtros e
  checksum informativo.

### Conversas e projetos

- O modelo recebe o histórico real da conversa e da ramificação selecionada.
- Conflitos entre o projeto da conversa e o projeto solicitado retornam erro,
  evitando mistura silenciosa de contextos.
- O `request_id` real do streaming é persistido para correlação com operações.
- Projeto ativo aparece no chat e pode ser conectado explicitamente a uma
  conversa existente.

### Segurança

- O inspetor nunca devolve valores completos de mensagens, memórias,
  documentos, anexos ou ações.
- A ação mostrada no manifesto passa pela mesma sanitização usada antes do
  envio ao modelo.
- Exportações continuam passando pela redação compartilhada de credenciais.
- Modos restritivos bloqueiam tipos de ação desconhecidos por padrão.

## 4.1.0 — Control Center

### Controle e confiança

- Central de operações com estados reais, recursos afetados, eventos e ações
  de aprovar, cancelar, repetir ou desfazer conforme a capacidade da ferramenta.
- Políticas de permissão por escopo: perguntar, permitir na sessão ou bloquear.
- Streaming SSE com tokens, etapas, ações, operações, conclusão, erro e
  cancelamento vinculados ao mesmo `request_id`.
- Cancelamento propagado do renderer ao processo Electron, núcleo e cliente do
  provedor, sem converter respostas parciais em sucesso.
- Registro limitado e sanitizado para não persistir payloads executáveis ou
  segredos como histórico reutilizável.

### Conhecimento e conversa

- Memórias globais e de projeto realmente incluídas no contexto do modelo.
- CRUD completo de memórias, incluindo ativação e desativação.
- Projetos com instruções, conversas, documentos e memória separados.
- Importação de PDF, DOCX, XLSX, CSV, TSV, HTML e arquivos de texto; OCR
  opcional para páginas escaneadas.
- Busca local por trechos com referências de documento, página, planilha e
  intervalo de células quando disponíveis.
- Histórico unificado em SQLite, mensagens editáveis, ramificações e comparação
  de respostas regeneradas.

### Pesquisa, modelos e automações

- Pesquisa cuja abertura de páginas usa transporte com DNS/IP pinado no
  connect, ignora proxies do ambiente, valida redirecionamentos, extrai
  metadados e diferencia conteúdo completo de fallback por snippet.
- Fontes com título, domínio, data, URL e indicação heurística de conflitos.
- Perfis rápido, equilibrado, profundo, visão e offline, com orçamento,
  métricas e fallback.
- Automações de horário, arquivo, evento e condição, com simulação, histórico,
  tentativas e aprovação para ações externas.

### Interface e desktop

- Páginas interativas para Central de Controle, Memória, Projetos, Pesquisa,
  Modelos, Automações, Skills, Plugins, Tarefas, Workspace e Computador.
- Painel contextual para plano, fontes, anexos e ações; resultados de
  ferramentas e anexos exibidos como cards.
- Markdown com tabelas, código destacado e navegação por teclado aprimorada.
- Bandeja, atalho global, notificações, protocolo `aether://`, seleção nativa de
  arquivos/pastas e captura de tela ou região.
- Cofre de credenciais baseado no `safeStorage` do Electron, ativado somente
  quando a criptografia oferecida pelo sistema for adequada.
- Primeira abertura do pacote prepara uma `venv` privada e instala as
  dependências do núcleo, com verificação por hash e sem registrar a saída do
  instalador que possa conter credenciais de proxy/índice.
- Texto auxiliar com mínimo de 12 px e cores semânticas do tema claro ajustadas
  para contraste WCAG AA.

### Limitações conhecidas

- Os pacotes Electron ainda exigem Python 3.10+ no sistema e acesso inicial ao
  índice/cache `pip`; o runtime Python completo não está incorporado.
- Plugins Python permanecem no processo principal e devem ser considerados
  código confiável; isolamento por subprocesso/contêiner está planejado.
- A automação Chromium está desativada em modo fail-closed até existir um proxy
  de saída isolado, auditável e com DNS/IP pinado.
- OCR exige `pytesseract` e o executável Tesseract instalados.
- O cancelamento interrompe imediatamente a interface, o transporte SSE e
  operações cooperativas; alguns workers síncronos podem terminar internamente
  em segundo plano.

## 4.0.0 — Professional Refresh

### Interface

- Nova experiência de chat com identidade visual Aether.
- Sidebar recolhível, pesquisa, favoritos e gestão de conversas.
- Tema claro/escuro/sistema, densidade, tipografia e movimento reduzido.
- Composer responsivo com anexos, voz, atalhos e interrupção.
- Extração segura de texto de PDFs anexados e MIME correto para imagens.
- Markdown seguro, código copiável, exportação e importação.
- Painel de contexto, telemetria, atividades, tarefas, skills e plugins.
- Paleta de comandos, toasts, modais acessíveis e navegação por teclado.
- Novo ícone, splash e recursos do instalador.

### Núcleo

- API renomeada e versionada como Aether Core 4.0.
- Catálogo `/capabilities`, diagnóstico `/diagnostics`, progresso
  `/chat/stream` e resumo `/memory/sessions`.
- Cancelamento por identificador impede a execução de ações ainda pendentes.
- Seletor nativo de workspace e resultados compactos de ferramentas no chat.
- Sessões compactas de memória e limites explícitos para mensagens.
- Empacotamento Python corrigido e comando `aether-core`.

### Segurança

- Token local aleatório por inicialização e ponte IPC isolada.
- Segredos removidos dos arquivos de exemplo.
- Confirmação de operações destrutivas e efeitos externos.
- Plugins não executam automaticamente na instalação.
- Bloqueio de SSRF e esquemas de URL inseguros.
- Processos exigem nome válido e correspondência exata.
- Backups ignoram segredos e bloqueiam Zip Slip, links e arquivos excessivos.
- Faces usam nomes sanitizados.
- Planos e checkpoints ficam vinculados ao workspace de origem.
- Tokens Gmail e Calendar foram separados.
- Chave de clima não reutiliza credenciais de modelos.
- Ações completas e resultados sensíveis permanecem somente na memória da
  sessão; histórico/importação guardam resumos não executáveis.
- Limites de tamanho e quantidade para PDFs, listagens e backups.
