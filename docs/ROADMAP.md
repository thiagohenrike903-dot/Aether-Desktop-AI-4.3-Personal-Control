# Roadmap técnico

## Entregue até a versão 4.3

- Interface monocromática oficial, responsiva, acessível e com avatar Aether.
- Painel inicial independente para Trabalho, Estudo e Pessoal, com módulos,
  atalhos, projetos e automações fixados.
- Modo foco, largura de leitura, espaçamento, tipografia alternativa, alto
  contraste e tamanho de código salvos por perfil.
- Capas locais monocromáticas e determinísticas para projetos.
- Linha do tempo operacional recolhível dentro das respostas, sem expor
  raciocínio privado do modelo.
- Regeneração, ramificações e comparação A/B com diferenças destacadas.
- Métricas por resposta — duração, tokens, custo estimado e primeiro token
  somente quando ele foi realmente medido.
- Central de Controle, permissões, modos globais de proteção, políticas por
  projeto e suspensão emergencial de automações e plugins.
- Inspetor de contexto, exclusões antes da regeneração, perfil 100% local e
  mapa de privacidade por conversa e global.
- Auditoria pesquisável, exportação JSON/Markdown e cadeia de integridade
  interna.
- Central de conexões e cofre do sistema operacional com concessões por
  integração, inclusive temporárias e de sessão.
- Model Lab paralelo, presets pessoais, seleção da vencedora e criação de
  perfil reutilizável.
- Workflows versionados, variáveis tipadas, simulação, restauração e conversão
  de operações concluídas.
- Biblioteca de projeto com PDF, DOCX, XLSX, CSV, páginas, pastas, OCR
  opcional, duplicatas, versões e reindexação incremental.
- Índice semântico opcional e inteiramente local, sem download silencioso de
  modelos.
- Backup seletivo, validação prévia, criptografia opcional e restauração com
  snapshot.
- Atualizações verificadas com Ed25519/SHA-256, canais Estável/Testes,
  snapshots e reversão transacional.
- Verificador de respostas, saúde do sistema, modo de ensaio, avaliações
  pessoais e critérios explícitos de governança de agentes.

## Próximas evoluções de maior valor

### 1. Distribuição realmente autônoma

Incorporar um runtime Python e wheels verificados ao aplicativo, eliminando a
necessidade de Python instalado e de internet na primeira abertura. Assinar os
executáveis e o instalador em cada plataforma.

### 2. Instalação automática de atualizações

A 4.3 verifica manifestos e artefatos, escolhe canal, cria snapshots e reverte.
O próximo passo é baixar e aplicar uma atualização assinada com retomada,
progresso e reinício seguro, sem ampliar o conjunto de domínios permitidos.

### 3. Isolamento forte de plugins

Executar plugins em processos separados, com manifesto de permissões, protocolo
limitado, timeout, cotas de CPU/memória e assinatura do autor. A suspensão
atual impede novas execuções, mas não transforma código Python desconhecido em
código confiável.

### 4. Egress pinado para navegador persistente

Colocar o Chromium atrás de um proxy de saída isolado que valide e fixe IPs
públicos para páginas, redirecionamentos e subrecursos. Só então oferecer
sessões e cookies persistentes, diferenciando leitura de cliques,
preenchimentos e envios. Até lá, a automação Chromium permanece bloqueada.

### 5. Âncora externa de auditoria

Assinar checkpoints da cadeia de auditoria em uma chave ou serviço separado.
A cadeia interna da 4.3 detecta alterações comuns, mas um invasor com controle
total do banco poderia recalculá-la.

### 6. Aplicativo móvel real

Transformar os recursos compatíveis em PWA e, depois, empacotar Android/iOS.
Recursos exclusivos do computador devem permanecer explicitamente
indisponíveis no celular. O layout estreito atual é apenas responsivo.

### 7. Voz local empacotada

Adicionar transcrição offline, palavra de ativação opcional e modo mãos-livres
com indicador permanente de microfone, histórico de ativações e desligamento
global imediato.
