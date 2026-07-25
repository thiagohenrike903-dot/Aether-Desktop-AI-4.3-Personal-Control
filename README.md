# Aether Desktop AI 4.3 — Personal Control

Assistente de desktop local com interface profissional, múltiplos provedores de
IA, memória por projeto, biblioteca de documentos, pesquisa aprofundada e
automações protegidas por confirmação e uma identidade visual monocromática.

## O que mudou na versão 4.3

- **Painel pessoal:** organizações independentes para Trabalho, Estudo e
  Pessoal, com atalhos, módulos, projetos e automações fixados.
- **Modo foco e leitura:** recolhe os painéis e salva largura, espaçamento,
  tamanho do código, contraste e tipografia por perfil.
- **Linha do tempo na resposta:** ações, fontes, alterações e aprovações ficam
  em um histórico recolhível sem expor raciocínio privado do modelo.
- **Model Lab:** duas respostas usam o mesmo contexto, aparecem lado a lado e
  registram métricas reais ou explicitamente não medidas.
- **Controle e privacidade:** políticas por projeto, suspensão emergencial,
  perfil 100% local, mapa global/por conversa e auditoria pesquisável com cadeia
  de integridade interna.
- **Cofre por integração:** concessões permanentes, de sessão, temporárias ou
  bloqueadas; OAuth de Gmail e Calendar permanece em memória.
- **Workflows e ensaio:** templates versionados com variáveis, prévia,
  aprovação e invalidação quando um recurso afetado muda.
- **Biblioteca avançada:** reindexação incremental, duplicatas, versões e
  índice semântico local opcional.
- **Recuperação:** backups de usuário sem credenciais, snapshots transacionais
  e verificação de atualização Ed25519/SHA-256.
- **Confiabilidade:** verificador de respostas, saúde do sistema, avaliações
  pessoais e governança honesta de agentes indisponíveis.

Consulte [recursos da 4.3](docs/RECURSOS-4.3.md) e
[segurança e limitações](docs/SEGURANCA-E-LIMITACOES-4.3.md).

## Identidade visual e experiência 4.3

- **Identidade Aether oficial:** preto, branco e cinza em toda a interface,
  usando a wordmark original nos espaços amplos e o “A” da própria marca como
  avatar do assistente, ícone da janela, bandeja e splash.
- **Hierarquia visual refeita:** sidebar preta, área de leitura clara, topo com
  breadcrumb de projeto, página inicial editorial e painel contextual menos
  técnico. O tema escuro continua inteiramente monocromático.
- **Modo de proteção global:** escolha entre proteção padrão, confirmar toda
  ação conhecida ou somente leitura. O limite vale para chat, rotas diretas,
  repetição de operações e automações.
- **Inspetor de contexto e mapa de privacidade:** antes de enviar, mostra
  histórico, memórias, documentos, skills, anexos, estimativa de tokens e se o
  conteúdo pode sair do computador. Valores completos e segredos não entram no
  manifesto.
- **Auditoria exportável:** gera JSON redigido com operações e eventos,
  filtros temporais, contagens e checksum informativo.
- **Projetos visíveis no chat:** o projeto ativo aparece na sidebar e no topo;
  uma conversa pode ser vinculada explicitamente a um projeto sem apagar seu
  histórico.
- **Histórico por ramificação corrigido:** o contexto do modelo respeita a
  cadeia de mensagens da ramificação e rejeita conflitos entre conversa e
  projeto em vez de misturar dados.
- **Desktop mais integrado:** janela restaura posição e maximização, bandeja
  usa arte própria legível e o progresso das operações aparece na barra do
  sistema quando suportado.

## Prévias

As capturas em [`docs/previews`](docs/previews/README.md) foram renderizadas
diretamente pela interface 4.3 em Chromium. Os dados apresentados são fixtures
locais de documentação; o layout, a responsividade, os controles e os
componentes pertencem ao aplicativo:

- painel personalizado para Trabalho, Estudo e Pessoal;
- modo foco com timeline, verificação e comparação A/B;
- Model Lab com métricas e critérios de avaliação manual;
- auditoria pesquisável com estado anterior e posterior;
- saúde, reparos e recuperação;
- adaptação responsiva para telas estreitas.

## Recursos preservados da versão 4.1

- **Central de Controle:** operações aguardando aprovação, em execução,
  concluídas, canceladas ou com erro; recursos afetados; histórico; cancelar,
  aprovar, repetir e desfazer quando a ferramenta oferecer suporte.
- **Permissões por escopo:** perguntar sempre, permitir durante a sessão ou
  bloquear, sem transformar uma aprovação antiga em autorização permanente.
- **Streaming SSE real:** tokens e etapas chegam conforme o provedor e as
  ferramentas trabalham; o mesmo identificador acompanha geração, operação e
  cancelamento.
- **Memória conectada:** memórias globais e de projeto entram no contexto do
  chat e podem ser pesquisadas, editadas, desativadas ou excluídas.
- **Projetos e documentos:** conversas, instruções, memórias e arquivos ficam
  agrupados. A biblioteca lê PDF, DOCX, XLSX, CSV, TSV, páginas e texto, com
  trechos e localizações clicáveis.
- **Pesquisa aprofundada:** abre as páginas encontradas, registra título,
  domínio, data e URL, diferencia página completa de snippet e sinaliza
  possíveis divergências entre fontes.
- **Páginas de sistema:** Memória, Projetos, Skills, Plugins, Tarefas,
  Workspace, Modelos, Automações e Computador possuem telas próprias.
- **Perfis de modelo:** rápido, equilibrado, profundo, visão e offline, com
  seleção no chat, orçamento, métricas de uso e fallback configurável.
- **Automações visuais:** horário, arquivo, evento ou condição, com simulação,
  execuções registradas, novas tentativas e aprovação para efeitos externos.
- **Conversas ramificáveis:** edição, regeneração, ramificação e comparação de
  respostas, com histórico unificado no SQLite.
- **Painel contextual:** plano, fontes, anexos e ações substituem telemetria
  técnica durante a conversa; CPU e RAM ficam na página Computador.
- **Integração desktop:** bandeja, atalho global, notificações, protocolo
  `aether://`, seleção de arquivo/pasta e captura de tela ou região.
- **Cofre do sistema:** o Electron pode guardar credenciais com `safeStorage`
  quando o sistema operacional oferece criptografia adequada.

## Requisitos

- Node.js 22.12 ou superior.
- npm 10 ou superior.
- Python 3.10 ou superior.
- Windows 10/11, macOS ou Linux.

Alguns recursos são opcionais: visão computacional, Gmail, Google Calendar e
memória vetorial podem exigir pacotes ou credenciais adicionais. A automação de
navegador baseada em Chromium está desativada nesta versão por segurança; a
Pesquisa Profissional continua disponível para leitura de páginas públicas.

No aplicativo empacotado, a primeira abertura cria um ambiente Python privado
na pasta de dados do Aether e instala automaticamente os componentes do núcleo.
Essa etapa requer acesso à internet (ou um índice/cache `pip` já configurado).
O Python do sistema ainda é necessário porque o runtime não está incorporado.

## Início rápido

No terminal, dentro da pasta do projeto:

```bash
npm install
npm run setup
npm start
```

O comando `npm run setup`:

1. cria uma `.venv` local;
2. instala `python/requirements.txt`;
3. cria um `.env` vazio a partir do exemplo seguro.

Na primeira execução, use a configuração guiada. No aplicativo desktop, as
integrações que exigem segredo permanecem indisponíveis quando o cofre seguro do
sistema não puder ser usado; o modo protegido não recorre silenciosamente a
`.env`. O arquivo `.env` é aceito apenas ao executar o núcleo Python
separadamente para desenvolvimento. Nunca coloque chaves em `.env.example`.

### Windows sem terminal integrado

Abra a pasta no PowerShell e execute os mesmos três comandos. O Electron detecta
automaticamente `.venv\Scripts\python.exe`.

## Configuração principal

| Variável | Finalidade |
| --- | --- |
| `LLM_PROVIDER` | `gemini`, `glm`, `qwen`, `qwen_api`, `openai` ou `ollama` |
| `GEMINI_API_KEY` | Chave Gemini, quando esse provedor estiver ativo |
| `LLM_API_KEY` | Chave do provedor genérico compatível |
| `LLM_BASE_URL` | URL de uma API compatível com OpenAI |
| `LLM_MODEL` | Modelo específico do provedor |
| `OLLAMA_BASE_URL` | Servidor Ollama local |
| `ELEVENLABS_API_KEY` | Voz neural opcional |
| `WEATHER_API_KEY` | Clima e previsão do OpenWeather |
| `AETHER_TIMEZONE` | Fuso IANA opcional usado em eventos sem offset |
| `JARVIS_PYTHON` | Caminho manual do Python, caso necessário |
| `JARVIS_PORT` | Porta local do núcleo; padrão `8765` |

Os nomes `JARVIS_*` foram preservados para não quebrar integrações existentes.
Eles podem ser migrados em uma futura versão principal.

Durante a abertura pelo Electron, host, porta e token são fixados pela própria
ponte desktop para que o `.env` não consiga redirecionar a conexão protegida.
Para trocar a porta do aplicativo, defina `JARVIS_PORT` no ambiente antes de
executar `npm start`; o valor do `.env` continua disponível no uso direto do
núcleo Python.

## Comandos do projeto

| Comando | Resultado |
| --- | --- |
| `npm run setup` | Prepara Python, dependências e `.env` |
| `npm start` | Abre o aplicativo |
| `npm run check` | Valida JavaScript e arquivos de build |
| `npm run test:electron` | Testa streaming, cancelamento e ponte desktop |
| `npm run build:icons` | Regenera ícone, wordmark, tray e imagens do instalador |
| `npm run validate` | Sincroniza e valida todo o pacote local |
| `npm run build:renderer` | Copia a interface para `dist/` |
| `npm run prepare:update-trust` | Valida e instala a chave pública Ed25519 de atualização |
| `npm run pack` | Gera uma pasta de aplicativo para validação |
| `npm run build:win` | Gera instalador e versão portátil para Windows |
| `npm run build:win:trusted` | Exige a chave pública e gera o build Windows com confiança de atualização |

`npm run build:icons` requer Inkscape e ImageMagick. Os PNG, ICO e BMP gerados
ficam versionados no projeto, portanto usuários finais não precisam dessas
ferramentas para instalar ou executar o Aether.

Para um build de produção, forneça somente a **chave pública Ed25519**:

```powershell
$env:AETHER_UPDATE_PUBLIC_KEY_FILE="C:\caminho\update-public-key.pem"
npm run build:win:trusted
```

Nunca coloque a chave privada no projeto. Sem uma chave pública provisionada, o
Aether continua utilizável, mas a verificação e a instalação de atualizações
ficam explicitamente indisponíveis.

O instalador distribui o núcleo e prepara suas dependências automaticamente na
primeira abertura. Ele ainda não incorpora o próprio runtime Python e, portanto,
não é uma instalação totalmente offline. Consulte `docs/ROADMAP.md`.

### Rede e pesquisa

Ao abrir cada fonte, a Pesquisa Profissional ignora proxies definidos pelo
ambiente, rejeita qualquer resposta DNS que misture IP público e privado e
conecta diretamente a um dos IPs públicos validados. O hostname original
continua sendo usado no header HTTP `Host` e no SNI/certificado TLS. Cada
redirecionamento é validado e conectado da mesma forma.

As rotas de automação Chromium (`/browser/*`) respondem em modo bloqueado. A
interceptação de requisições do Playwright não elimina sozinha DNS rebinding;
essas funções só devem ser reativadas depois de existir um proxy de saída
pinado, isolado e auditável.

## Estrutura

```text
electron/        processo principal e ponte IPC segura
renderer/        interface HTML, CSS e JavaScript
python/jarvis/    núcleo FastAPI, agentes e integrações
python/tests/     testes do núcleo
build/            ícones, splash e configuração do instalador
docs/             roadmap técnico
```

## Segurança

O núcleo permanece em loopback e o aplicativo usa um token efêmero que não é
exposto ao renderer. Ações importantes passam pela política de permissões.
Mesmo assim, revise destinatários, caminhos, alterações de código, automações e
plugins antes de aprovar.

Leia [SECURITY.md](SECURITY.md) antes de habilitar plugins ou automações.
Os resultados do freeze estão em
[docs/VALIDACAO-4.3.md](docs/VALIDACAO-4.3.md).
As regras da marca estão em
[docs/IDENTIDADE-VISUAL.md](docs/IDENTIDADE-VISUAL.md), e as próximas
evoluções priorizadas em
[docs/PROXIMAS_IDEIAS.md](docs/PROXIMAS_IDEIAS.md).

## Solução de problemas

### “Núcleo offline”

Execute:

```bash
npm run setup
```

Depois verifique se a porta `8765` está livre e tente novamente pelo botão de
conexão.

### Modelo não configurado

No aplicativo, configure o provedor, o modelo e a chave pelo cofre em
**Conexões**. Use `.env` somente ao executar o núcleo Python separadamente para
desenvolvimento. O painel lateral mostra o estado sem revelar a credencial.

### Visão indisponível

Com a `.venv` ativa:

```bash
python -m pip install -r python/requirements-vision.txt
```

Reconhecimento facial e MediaPipe requerem Python 3.12 ou anterior. OCR também
requer o executável [Tesseract](https://github.com/tesseract-ocr/tesseract);
leitura de QR/código de barras requer a biblioteca nativa `zbar`. O painel
Diagnóstico informa separadamente quais módulos estão realmente disponíveis.

### Testes Python

Com a `.venv` ativa:

```bash
cd python
python -m pytest tests
```
