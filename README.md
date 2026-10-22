# SambaBox

Provisionador experimental de **Ubuntu Server + OpenSSH + Samba** sobre Oracle VirtualBox, operado a partir do Windows e mantido pela **Aray Soluções**.

> **Estado: pré-lançamento (experimental).** Confirmamos em laboratório uma VM Ubuntu conectada por bridge, autenticação SSH e acesso ao compartilhamento `Empresa` pelo Windows. A automação de primeiro boot ainda precisa de correções; o `cloud-init` apresentou falha no laboratório. Não recomendado para produção.

## Funcionalidades atuais

- Detectar VMs cujo nome contenha `Samba`.
- Criar uma VM, reaproveitar uma existente ou excluí-la com confirmação.
- Selecionar automaticamente uma interface bridge ativa reconhecida pelo VirtualBox.
- Baixar/reaproveitar uma imagem oficial do Ubuntu Cloud e conferir SHA-256.
- Criar VM e preparar inicialização por cloud-init.
- Localizar VM na LAN, autenticar por SSH, instalar/configurar Samba e verificar o serviço e a porta TCP/445.

## Requisitos

- Windows 10/11;
- Python 3.10 ou superior;
- Oracle VirtualBox 7.x, com driver de rede bridge ativo;
- DHCP e conectividade de rede local;
- acesso à internet na primeira configuração.

As dependências `pycdlib` e `paramiko` são instaladas sob demanda na implementação atual. Isso será substituído por dependências fixadas e ambiente isolado.

## Início rápido

```powershell
git clone https://github.com/araysolucoes/SambaBox.git
cd SambaBox
py sambabox.py
```

No menu: 1 cria outra VM, 2 reaproveita uma VM com credenciais válidas e 3 solicita confirmação para excluir e recriar. O comando legado `py aray_samba_virtualbox.py` encaminha para o novo gerenciador.

Após a verificação, o terminal informa IP e comandos para acesso, como:

```text
ssh aray@<IP_DA_VM>
\\<IP_DA_VM>\Empresa
```

O endereço IP depende do DHCP e não deve ser fixado na documentação.

## Segurança e limitações importantes

- **Não use como solução de produção** antes de corrigir e testar o primeiro boot, o tratamento de erros e o gerenciamento de credenciais.
- A implementação atual gera uma senha compartilhada para contas administrativas e Samba e a exibe no console. Isso precisa ser substituído por credenciais distintas, rotacionáveis e armazenamento seguro.
- A ISO de seed do cloud-init contém senha em texto claro: proteja o host, remova a mídia após uso e nunca faça commit de imagens ou segredos.
- O teste atual verifica SSH e a abertura da porta 445, **não é uma suíte completa de leitura/escrita/autorização SMB**.
- Não exponha a porta 445 à internet nem habilite autenticação SSH direta de root.
- A opção de exclusão remove a VM escolhida e seus discos registrados no VirtualBox. Confirme que não há dados importantes.
- A sondagem de IP supõe uma LAN IPv4 /24; redes com outros prefixos exigem melhorias.
- O VirtualBox, Ubuntu e Samba têm licenças e condições próprias; a licença deste repositório não substitui as licenças desses produtos.

## Documentação

- [Roadmap e arquitetura proposta](docs/ROADMAP.md)
- [Contribuindo](CONTRIBUTING.md)
- [Política de segurança](SECURITY.md)
- [Licença MIT](LICENSE)

## Desenvolvimento

O código atual está concentrado nos arquivos `sambabox.py` e `aray_samba_virtualbox.py`. A próxima etapa é uma refatoração incremental por módulos, preservando compatibilidade do comando legado e introduzindo testes com mocks para não depender de uma VM real em cada alteração.

Executar testes existentes:

```powershell
py -m unittest discover -v
```

## Licença

MIT — Copyright (c) 2026 Aray Soluções. Consulte [LICENSE](LICENSE).
