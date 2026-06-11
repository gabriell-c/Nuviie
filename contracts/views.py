import json
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404
from django.conf import settings

from audit.services import log_activity

from .models import GeneratedContract
from .nuviie_template import (
    FIELD_SCHEMA,
    PLACEHOLDER_LABELS,
    default_values,
    flat_field_schema,
    build_filled_data_from_post,
    preview_sections_for_js,
)
from .generator import generate_nuviie_contract_pdf
from .docx_generator import generate_nuviie_contract_docx


@login_required
def generate_view(request):
    """Gerador de contrato — modelo fixo Nuviie com preview ao vivo."""
    if request.method == 'POST':
        contract_name = request.POST.get('contract_name', '').strip() or 'Contrato de Prestação de Serviços'
        filled_data = build_filled_data_from_post(request.POST)
        export_format = request.POST.get('export_format', 'pdf')

        gen_dir = os.path.join(settings.MEDIA_ROOT, 'generated_contracts')
        os.makedirs(gen_dir, exist_ok=True)

        safe_name = ''.join(x for x in contract_name if x.isalnum() or x in ' -_').strip()
        base_filename = f'{request.user.id}_nuviie_{safe_name}'

        try:
            if export_format == 'docx':
                filename = f'{base_filename}.docx'
                output_filepath = os.path.join(gen_dir, filename)
                generate_nuviie_contract_docx(filled_data, output_filepath, contract_name)
            else:
                filename = f'{base_filename}.pdf'
                output_filepath = os.path.join(gen_dir, filename)
                generate_nuviie_contract_pdf(filled_data, output_filepath, contract_name)

            rel_file_path = f'generated_contracts/{filename}'
            contract = GeneratedContract.objects.create(
                user=request.user,
                template=None,
                name=contract_name,
                filled_data=filled_data,
                pdf_file=rel_file_path,
            )

            log_activity(
                'contract_generate',
                f"Contrato '{contract_name}' gerado ({export_format.upper()}).",
                user=request.user,
                entity_type='contract',
                entity_id=contract.pk,
                metadata={'format': export_format, 'template': 'Nuviie padrão'},
                request=request,
            )

            messages.success(request, f"Contrato '{contract_name}' gerado com sucesso!")
            if export_format == 'docx':
                return redirect('download_contract', contract_id=contract.id)
            return redirect('contracts_history')

        except Exception as e:
            messages.error(request, f'Falha ao gerar contrato: {e}')

    return render(request, 'contracts/generate.html', {
        'field_schema': FIELD_SCHEMA,
        'field_schema_json': json.dumps(FIELD_SCHEMA),
        'sections_json': json.dumps(preview_sections_for_js()),
        'defaults_json': json.dumps(default_values()),
        'placeholder_labels_json': json.dumps(PLACEHOLDER_LABELS),
        'current_page': 'contracts',
    })


@login_required
def contracts_history_view(request):
    contracts = GeneratedContract.objects.filter(user=request.user)
    return render(request, 'contracts/history.html', {
        'contracts': contracts,
        'current_page': 'contracts',
    })


@login_required
def delete_contract_view(request, contract_id):
    contract = get_object_or_404(GeneratedContract, id=contract_id, user=request.user)
    name = contract.name
    if contract.pdf_file and os.path.exists(contract.pdf_file.path):
        os.remove(contract.pdf_file.path)

    log_activity(
        'contract_delete',
        f"Contrato '{name}' removido do histórico.",
        user=request.user,
        entity_type='contract',
        entity_id=contract_id,
        request=request,
    )
    contract.delete()
    messages.success(request, f"Documento '{name}' removido do histórico.")
    return redirect('contracts_history')


@login_required
def download_contract_view(request, contract_id):
    contract = get_object_or_404(GeneratedContract, id=contract_id, user=request.user)

    if not contract.pdf_file or not os.path.exists(contract.pdf_file.path):
        raise Http404('Arquivo de contrato não encontrado.')

    log_activity(
        'contract_download',
        f"Download do contrato '{contract.name}'.",
        user=request.user,
        entity_type='contract',
        entity_id=contract_id,
        request=request,
    )

    ext = os.path.splitext(contract.pdf_file.path)[1].lower()
    content_type = (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        if ext == '.docx' else 'application/pdf'
    )
    response = FileResponse(open(contract.pdf_file.path, 'rb'), content_type=content_type)
    safe_filename = contract.name.replace(' ', '_') + ext
    response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
    return response
