"""Modelo fixo — Contrato de Prestação de Serviços Nuviie."""

from __future__ import annotations

import re
from copy import deepcopy

# Campos do formulário agrupados por seção
FIELD_SCHEMA: list[dict] = [
    {
        'group': 'Identificação do documento',
        'fields': [
            {'key': 'contract_name', 'label': 'Nome interno do documento', 'type': 'text',
             'default': 'Contrato de Prestação de Serviços', 'required': True},
        ],
    },
    {
        'group': 'Dados do contratante (cliente)',
        'fields': [
            {'key': 'nome_cliente', 'label': 'Nome / Razão Social', 'type': 'text', 'required': True},
            {'key': 'tipo_pessoa', 'label': 'Tipo', 'type': 'select',
             'options': ['Pessoa Física', 'Pessoa Jurídica'], 'default': 'Pessoa Jurídica'},
            {'key': 'cpf_cnpj', 'label': 'CPF / CNPJ', 'type': 'text', 'required': True},
            {'key': 'endereco', 'label': 'Endereço completo', 'type': 'text', 'required': True},
            {'key': 'representante', 'label': 'Cargo / Representante legal', 'type': 'text',
             'default': 'Representante Legal'},
        ],
    },
    {
        'group': 'Escopo do projeto',
        'fields': [
            {'key': 'plataforma', 'label': 'Plataforma', 'type': 'text',
             'default': 'WordPress', 'placeholder': 'Ex: WordPress, Webflow...'},
            {'key': 'num_paginas', 'label': 'Número de páginas', 'type': 'number', 'default': '5'},
            {'key': 'paginas_lista', 'label': 'Páginas incluídas', 'type': 'text',
             'default': 'Home, Sobre, Serviços/Produtos, Blog e Contato'},
        ],
    },
    {
        'group': 'Prazos',
        'fields': [
            {'key': 'prazo_materiais_dias', 'label': 'Prazo entrega de materiais (dias úteis)', 'type': 'number', 'default': '7'},
            {'key': 'prazo_desenvolvimento_dias', 'label': 'Prazo de desenvolvimento (dias úteis)', 'type': 'number', 'default': '30'},
        ],
    },
    {
        'group': 'Valores e pagamento',
        'fields': [
            {'key': 'modelo_pagamento', 'label': 'Modelo de pagamento', 'type': 'select',
             'options': [
                 ('vista_antes', 'À vista — antes da entrega'),
                 ('vista_depois', 'À vista — após a entrega'),
                 ('parcelado', 'Parcelado (cartão)'),
                 ('metade_antes_depois', 'Metade antes / metade depois'),
             ],
             'default': 'vista_antes'},
            {'key': 'vista_quando', 'label': 'À vista (quando)', 'type': 'select',
             'options': ['antes', 'depois'], 'default': 'antes'},
            {'key': 'primeiro_vencimento', 'label': '1º vencimento / pagamento', 'type': 'date'},
            {'key': 'data_assinatura_iso', 'label': 'Data assinatura (ISO)', 'type': 'date'},
            {'key': 'valor_total', 'label': 'Valor total (R$)', 'type': 'money', 'required': True},
            {'key': 'valor_total_extenso', 'label': 'Valor total por extenso', 'type': 'text'},
            {'key': 'valor_vista', 'label': 'Valor à vista com desconto (R$)', 'type': 'money'},
            {'key': 'valor_vista_extenso', 'label': 'Valor à vista por extenso', 'type': 'text'},
            {'key': 'desconto_percentual', 'label': 'Desconto à vista (%)', 'type': 'number', 'default': '10'},
            {'key': 'parcelas_cartao', 'label': 'Parcelas no cartão', 'type': 'number', 'default': '12'},
            {'key': 'acrescimo_cartao_percentual', 'label': 'Acréscimo cartão (%)', 'type': 'number', 'default': '5'},
        ],
    },
    {
        'group': 'Assinatura',
        'fields': [
            {'key': 'cidade_assinatura', 'label': 'Cidade', 'type': 'text', 'default': 'Ribeirão Preto'},
            {'key': 'data_assinatura', 'label': 'Data por extenso', 'type': 'text',
             'placeholder': 'Ex: 15 de março de 2026'},
            {'key': 'assinatura_contratante', 'label': 'Linha de assinatura do contratante',
             'type': 'text', 'placeholder': 'Nome - Empresa do Contratante'},
        ],
    },
]

# Labels exibidos no preview quando o campo está vazio (igual ao PDF original)
PLACEHOLDER_LABELS: dict[str, str] = {
    'nome_cliente': 'NOME/RAZÃO SOCIAL DO CLIENTE',
    'tipo_pessoa': 'PESSOA FÍSICA/JURÍDICA',
    'cpf_cnpj': 'CPF/CNPJ',
    'endereco': 'ENDEREÇO COMPLETO',
    'representante': 'CARGO/REPRESENTANTE LEGAL',
    'plataforma': 'ESPECIFICAR PLATAFORMA',
    'num_paginas': 'NÚMERO',
    'paginas_lista': 'Home, Sobre, Serviços/Produtos, Blog e Contato',
    'prazo_materiais_dias': 'XX',
    'prazo_desenvolvimento_dias': 'XX',
    'valor_total': 'VALOR',
    'valor_total_extenso': 'EXTENSO',
    'valor_vista': 'VALOR COM DESCONTO',
    'valor_vista_extenso': 'EXTENSO',
    'desconto_percentual': 'XX',
    'parcelas_cartao': 'XX',
    'acrescimo_cartao_percentual': 'XX',
    'cidade_assinatura': 'Ribeirão Preto',
    'data_assinatura': 'xx de mês de ano',
    'assinatura_contratante': 'Nome CONTRATANTE - EMPRESA DO CONTRATANTE',
}

NUVIIE_BLUE = '#00758a'

# Parágrafos do contrato — placeholders {{chave}}
# style: title | intro | party_label | body | clause
CONTRACT_SECTIONS: list[dict] = [
    {'style': 'title', 'text': 'CONTRATO DE PRESTAÇÃO DE SERVIÇOS'},
    {'style': 'intro', 'text': 'Pelo presente instrumento particular, celebrado entre:'},
    {'style': 'party_label', 'text': 'DE UMA PARTE:'},
    {'style': 'body', 'text': (
        'NUVIIE, pessoa física, profissional autônoma, inscrita no CPF sob o nº '
        '497.097.338-50, com domicílio profissional na cidade de Ribeirão Preto/SP, '
        'doravante denominada CONTRATADA;'
    )},
    {'style': 'party_label', 'text': 'E DE OUTRA PARTE:'},
    {'style': 'body', 'text': (
        '{{nome_cliente}}, {{tipo_pessoa}}, inscrito(a) no {{cpf_cnpj}}, '
        'com sede/domicílio à {{endereco}}, neste ato representado(a) por seu(sua) '
        '{{representante}}, doravante denominado(a) CONTRATANTE;'
    )},
    {'style': 'body', 'text': (
        'As partes acima qualificadas, de comum acordo e na melhor forma de direito, '
        'celebram o presente Contrato de Prestação de Serviços de Desenvolvimento Web, '
        'que se regerá pelas seguintes cláusulas e condições:'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA PRIMEIRA - DO OBJETO'},
    {'style': 'body', 'text': (
        'O CONTRATANTE resolve contratar os serviços da CONTRATADA para o desenvolvimento '
        'completo de website institucional, conforme especificações técnicas detalhadas no '
        'presente instrumento. O website será desenvolvido na plataforma {{plataforma}}, '
        'contendo {{num_paginas}} páginas principais, sendo elas: {{paginas_lista}}, com '
        'layout responsivo adaptável a todos os dispositivos móveis.'
    )},
    {'style': 'body', 'text': (
        'A CONTRATADA se compromete a entregar website completo e funcional, incluindo '
        'integração com ferramentas de análise (Google Analytics e Search Console), '
        'configuração básica de SEO (meta tags, títulos e descrições otimizadas) e suporte '
        'técnico por período de 14 (quatorze) dias corridos após a entrega final, '
        'exclusivamente para correção de eventuais bugs de funcionamento.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA SEGUNDA - DAS OBRIGAÇÕES DA CONTRATADA'},
    {'style': 'body', 'text': (
        'A CONTRATADA se obriga a desenvolver o website conforme especificações acordadas, '
        'utilizando tecnologias atualizadas e compatíveis com os padrões web vigentes. '
        'Compromete-se a implementar medidas básicas de segurança digital e a entregar '
        'documentação técnica contendo todas as credenciais de acesso ao sistema desenvolvido.'
    )},
    {'style': 'body', 'text': (
        'A CONTRATADA deverá manter estrito sigilo sobre todas as informações, dados e '
        'materiais confidenciais do CONTRATANTE, nos termos da cláusula de confidencialidade '
        'constante no presente instrumento. Todas as etapas do desenvolvimento serão submetidas '
        'à aprovação do CONTRATANTE, que deverá se manifestar dentro do prazo de 48 (quarenta e oito) horas úteis.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA TERCEIRA - DAS OBRIGAÇÕES DO CONTRATANTE'},
    {'style': 'body', 'text': (
        'Ao CONTRATANTE compete fornecer todo o conteúdo necessário (textos, informações '
        'institucionais, imagens) em formato digital adequado, dentro do prazo de '
        '{{prazo_materiais_dias}} dias úteis contados da assinatura do contrato. O CONTRATANTE '
        'responderá civil e criminalmente por todo conteúdo fornecido, garantindo sua '
        'originalidade e conformidade com a legislação aplicável.'
    )},
    {'style': 'body', 'text': (
        'O CONTRATANTE deverá designar um representante com poder decisório para aprovações '
        'e comunicação com a CONTRATADA, bem como contratar, por conta própria, os serviços de '
        'hospedagem web com requisitos mínimos especificados pela CONTRATADA e registro de '
        'domínio junto a registrar credenciado.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA QUARTA - DOS PRAZOS'},
    {'style': 'body', 'text': (
        'O prazo total para desenvolvimento é de {{prazo_desenvolvimento_dias}} dias úteis, '
        'contados a partir da data de assinatura do contrato, do recebimento do pagamento '
        'inicial e da entrega completa de materiais pelo CONTRATANTE. Eventuais atrasos na '
        'entrega de materiais pelo CONTRATANTE acarretarão prorrogação proporcional do prazo '
        'final de entrega.'
    )},
    {'style': 'body', 'text': (
        'A CONTRATADA se compromete a informar imediatamente o CONTRATANTE sobre qualquer '
        'eventualidade que possa impactar no cronograma estabelecido, propondo as medidas '
        'cabíveis para mitigação dos atrasos.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA QUINTA - DA REMUNERAÇÃO'},
    {'style': 'body', 'text': (
        'Pelo fiel cumprimento do objeto contratual, o CONTRATANTE pagará à CONTRATADA o valor '
        'total de R$ {{valor_total}} ({{valor_total_extenso}}), que poderá ser liquidado das '
        'seguintes formas:\n'
        'a) À vista, através de PIX, no valor de R$ {{valor_vista}} ({{valor_vista_extenso}}), '
        'com desconto de {{desconto_percentual}}%;\n'
        'b) Parcelado em 2 (duas) vezes iguais, sendo 50% no ato da contratação e 50% na '
        'entrega do projeto;\n'
        'c) Através de cartão de crédito, em até {{parcelas_cartao}} parcelas mensais, com '
        'acréscimo de {{acrescimo_cartao_percentual}}% sobre o valor total.'
    )},
    {'style': 'body', 'text': (
        'O website somente será liberado para o CONTRATANTE após a quitação total dos valores '
        'devidos. Em caso de atraso no pagamento, ficará automaticamente suspenso o acesso aos '
        'sistemas até a regularização da situação.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA SEXTA - DA PROPRIEDADE INTELECTUAL'},
    {'style': 'body', 'text': (
        'A CONTRATADA mantém os direitos sobre o código-fonte até a quitação total do contrato. '
        'Após o pagamento integral, o CONTRATANTE receberá licença perpétua de uso não-exclusiva '
        'do sistema desenvolvido.'
    )},
    {'style': 'body', 'text': (
        'As partes concordam que a CONTRATADA poderá utilizar imagens do projeto finalizado '
        '(exceto conteúdo confidencial) para fins de portfólio e divulgação de seus serviços, '
        'desde que não revele informações sensíveis do CONTRATANTE.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA SÉTIMA - DA CONFIDENCIALIDADE'},
    {'style': 'body', 'text': (
        'As partes comprometem-se a manter sigilo sobre todas as informações confidenciais a '
        'que tiverem acesso durante a vigência contratual e após seu término. Consideram-se '
        'confidenciais todas as informações técnicas, comerciais, estratégicas ou operacionais '
        'de cada parte, que não sejam de conhecimento público.'
    )},
    {'style': 'body', 'text': (
        'O dever de confidencialidade permanecerá válido mesmo após a extinção do contrato, '
        'exceto quanto a informações que venham a se tornar públicas por outros meios que não '
        'violação do presente acordo.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA OITAVA - DA RESCISÃO'},
    {'style': 'body', 'text': (
        'Em caso de rescisão contratual por iniciativa do CONTRATANTE, serão aplicadas as '
        'seguintes condições:\n'
        'a) Se ocorrida antes do início dos trabalhos: devolução integral de valores '
        'eventualmente pagos;\n'
        'b) Se ocorrida após o início: pagamento proporcional aos serviços já executados;'
    )},
    {'style': 'body', 'text': (
        'A CONTRATADA poderá rescindir o contrato em caso de inadimplemento do CONTRATANTE por '
        'período superior a 15 (quinze) dias, sem prejuízo da cobrança dos valores devidos e de '
        'eventual indenização por perdas e danos.'
    )},
    {'style': 'clause', 'text': 'CLÁUSULA NONA - DO FORO'},
    {'style': 'body', 'text': (
        'Para dirimir quaisquer controvérsias oriundas do presente contrato, as partes elegem '
        'o foro da Comarca de Ribeirão Preto/SP, com expressa renúncia a qualquer outro, por '
        'mais privilegiado que seja.'
    )},
    {'style': 'body', 'text': (
        'E por estarem justas e acordadas, as partes assinam o presente instrumento em 2 vias '
        'de igual teor e forma, a serem enviadas pela plataforma de assinatura eletrônica Autentique.'
    )},
    {'style': 'signature', 'text': '{{cidade_assinatura}}, {{data_assinatura}}.'},
    {'style': 'signature', 'text': '{{assinatura_contratante}}'},
    {'style': 'signature', 'text': 'Gabriel Cardoso - Nuviie'},
]

_PLACEHOLDER_RE = re.compile(r'\{\{(\w+)\}\}')


def flat_field_schema() -> list[dict]:
    """Lista plana de campos para o formulário."""
    fields = []
    for group in FIELD_SCHEMA:
        for field in group['fields']:
            fields.append({**field, 'group': group['group']})
    return fields


def default_values() -> dict[str, str]:
    values = {}
    for field in flat_field_schema():
        if field.get('default') is not None:
            values[field['key']] = str(field['default'])
        else:
            values[field['key']] = ''
    return values


def render_paragraph(text: str, data: dict) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        val = data.get(key, '')
        if val:
            return str(val)
        label = PLACEHOLDER_LABELS.get(key, key.replace('_', ' ').upper())
        return f'!{label}!'
    return _PLACEHOLDER_RE.sub(replacer, text)


def render_sections(data: dict) -> list[dict]:
    """Retorna seções com texto já preenchido."""
    result = []
    for section in CONTRACT_SECTIONS:
        style = section.get('style', 'body')
        result.append({
            'style': style,
            'heading': style in ('title', 'clause', 'party_label'),
            'text': render_paragraph(section['text'], data),
        })
    return result


def render_paragraphs(data: dict) -> list[str]:
    return [s['text'] for s in render_sections(data) if s['text'].strip()]


def build_filled_data_from_post(post_data) -> dict[str, str]:
    data = default_values()
    for field in flat_field_schema():
        key = field['key']
        if key == 'contract_name':
            continue
        val = post_data.get(f'field_{key}', '').strip()
        if val:
            data[key] = val
    return data


def preview_sections_for_js() -> list[dict]:
    """Seções com placeholders {{key}} para substituição no Alpine."""
    return deepcopy(CONTRACT_SECTIONS)
