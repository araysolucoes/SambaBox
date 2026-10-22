# Roadmap técnico — SambaBox

Este documento descreve **trabalho proposto**, não recursos implementados. Prioridades podem mudar conforme testes reais.

## P0 — Segurança e confiabilidade (bloqueadores)

- [ ] Corrigir definitavamente erros de cloud-init; gerar `user-data` válido e testá-lo.
- [ ] Checar a configuração do Ubuntu e o resultado do provisionamento antes de declarar sucesso.
- [ ] Garantir identificação do IP por MAC e DHCP, sem varredura fixa em /24 e sem usar máquina incorreta.
- [ ] Separar credenciais Linux, root, SSH e Samba; usar chaves SSH quando possível.
- [ ] Eliminar exposição de credenciais em console/logs; descarte seguro do seed ISO.
- [ ] Pinagem de dependências, isolamento em venv e tratamento de indisponibilidade da internet.
- [ ] Implementar testes idempotentes de configuração, estado da VM, rollback e exclusão segura.
- [ ] Validar autenticação SMB e leitura/gravação em compartilhamento temporário.

**Critério de aceite:** instalação reproduzível em VM limpa; SSH e Samba autenticados, serviço ativo e operação SMB de leitura/escrita testada; falhas com diagnóstico preciso, sem vazamento de credenciais.

## P1 — Refatoração modular e testes

Organização de destino (proposta):

```text
sambabox/
  __init__.py
  cli.py                    # fluxo interativo; argumentos e mensagens
  application/
    provision.py            # orquestra fases e recuperação
    vm_service.py           # ciclo de vida das VMs
    samba_service.py        # tarefas de configuração e verificação
  domain/
    models.py               # VM, estados, recursos e parâmetros
    errors.py               # exceções com mensagem e causa
  infrastructure/
    virtualbox.py           # adaptador VBoxManage
    ubuntu_images.py        # download e SHA256
    cloud_init.py           # NoCloud e ISO
    ssh.py                  # conexão autenticada
    networking.py           # bridge, endereçamento e descoberta IP
    credentials.py          # criação e armazenamento temporário
  presentation/
    console.py              # prompts e resultados
tests/
  unit/
  integration/
docs/
  ARCHITECTURE.md
  TROUBLESHOOTING.md
```

O arquivo histórico `aray_samba_virtualbox.py` deverá permanecer como ponto de entrada compatível.

## P2 — Experiência do usuário

- [ ] Comandos `list`, `create`, `repair`, `status`, `delete`, `doctor`, `--help`.
- [ ] Indicadores por fase, mensagens claras, logs com dados sensíveis mascarados.
- [ ] Seleção automática da interface com opção de substituição explícita.
- [ ] Recuperação de instalações interrompidas sem precisar excluir a VM.
- [ ] Suporte a interfaces e sub-redes variadas (Ethernet/Wi-Fi e prefixos configuráveis).
- [ ] Exportar relatório de validação sem senhas.

## P3 — Administração de Samba

- [ ] Gestão de compartilhamentos, grupos, ACLs e quotas.
- [ ] Backup/restauração e trilha de auditoria.
- [ ] Health checks, atualização de pacotes e inventário de VMs.
- [ ] Interface gráfica apenas depois de o núcleo estar testado e desacoplado.

## Engenharia e publicação

- [ ] CI (ruff, análise de dependências, `unittest`, testes de integração com mocks).
- [ ] `pyproject.toml` com versões fixadas, entrypoint `sambabox` e metadados da licença.
- [ ] Política de versionamento SemVer e CHANGELOG.
- [ ] Primeiro release de prévia somente após P0.
