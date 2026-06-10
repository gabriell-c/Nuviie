import json
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST

from audit.services import log_activity

from .models import ContractTemplate, GeneratedContract
from .parser import analyze_contract_pdf
from .generator import generate_contract_pdf
from .docx_generator import generate_contract_docx


def _apply_analysis(template: ContractTemplate, pdf_path: str) -> int:
    result = analyze_contract_pdf(pdf_path)
    template.detected_fields = result['detected_fields']
    template.structure = result['structure']
    template.field_schema = result['field_schema']
    template.save()
    return len(result['detected_fields'])


def _build_filled_data(template: ContractTemplate, post_data) -> dict:
    filled_data = {}
    schema = template.field_schema or []
    if schema:
        for field in schema:
            key = field.get('key', '')
            if key:
                filled_data[key] = post_data.get(f'field_{key}', '').strip()
    else:
        for field in template.detected_fields:
            filled_data[field] = post_data.get(f'field_{field}', '').strip()
    return filled_data


@login_required
def template_list_view(request):
    templates = ContractTemplate.objects.filter(user=request.user)

    if request.method == 'POST' and 'upload_template' in request.POST:
        name = request.POST.get('name', '').strip()
        pdf_file = request.FILES.get('pdf_file')

        if not name or not pdf_file:
            messages.error(request, "Por favor, defina um nome e envie um arquivo PDF.")
            return redirect('template_list')

        if not pdf_file.name.endswith('.pdf'):
            messages.error(request, "Apenas arquivos PDF são permitidos.")
            return redirect('template_list')

        template = ContractTemplate.objects.create(
            user=request.user,
            name=name,
            pdf_file=pdf_file,
        )

        count = _apply_analysis(template, template.pdf_file.path)

        log_activity(
            'contract_template_upload',
            f"Template '{name}' enviado ({count} campos detectados).",
            user=request.user,
            entity_type='template',
            entity_id=template.pk,
            request=request,
        )

        messages.success(request, f"Template '{name}' cadastrado! {count} campos dinâmicos identificados.")
        return redirect('fill_template', template_id=template.id)

    return render(request, 'contracts/templates_list.html', {
        'templates': templates,
        'current_page': 'contracts',
    })


@login_required
@require_POST
def reanalyze_template_view(request, template_id):
    template = get_object_or_404(ContractTemplate, id=template_id, user=request.user)
    count = _apply_analysis(template, template.pdf_file.path)
    messages.success(request, f"Modelo reanalisado — {count} campos detectados.")
    return redirect('template_list')


@login_required
def delete_template_view(request, template_id):
    template = get_object_or_404(ContractTemplate, id=template_id, user=request.user)
    name = template.name
    if template.pdf_file and os.path.exists(template.pdf_file.path):
        os.remove(template.pdf_file.path)

    log_activity(
        'contract_template_delete',
        f"Template '{name}' excluído.",
        user=request.user,
        entity_type='template',
        entity_id=template_id,
        request=request,
    )
    template.delete()
    messages.success(request, f"Template '{name}' removido com sucesso.")
    return redirect('template_list')


@login_required
def fill_template_view(request, template_id):
    template = get_object_or_404(ContractTemplate, id=template_id, user=request.user)
    schema = template.field_schema or [
        {'key': k, 'label': k.replace('_', ' ').title(), 'type': 'text', 'default': ''}
        for k in template.detected_fields
    ]

    if request.method == 'POST':
        contract_name = request.POST.get('contract_name', '').strip() or f"Contrato - {template.name}"
        filled_data = _build_filled_data(template, request.POST)
        export_format = request.POST.get('export_format', 'pdf')

        gen_dir = os.path.join(settings.MEDIA_ROOT, 'generated_contracts')
        os.makedirs(gen_dir, exist_ok=True)

        safe_name = "".join(x for x in contract_name if x.isalnum() or x in " -_").strip()
        base_filename = f"{request.user.id}_{template.id}_{safe_name}"

        try:
            if export_format == 'docx':
                filename = f"{base_filename}.docx"
                output_filepath = os.path.join(gen_dir, filename)
                generate_contract_docx(
                    template.structure,
                    filled_data,
                    output_filepath,
                    contract_name,
                )
                rel_file_path = f"generated_contracts/{filename}"
            else:
                filename = f"{base_filename}.pdf"
                output_filepath = os.path.join(gen_dir, filename)
                generate_contract_pdf(
                    template_path=template.pdf_file.path,
                    filled_data=filled_data,
                    output_path=output_filepath,
                    contract_title=contract_name,
                    structure=template.structure,
                )
                rel_file_path = f"generated_contracts/{filename}"

            contract = GeneratedContract.objects.create(
                user=request.user,
                template=template,
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
                metadata={'format': export_format, 'template': template.name},
                request=request,
            )

            messages.success(request, f"Contrato '{contract_name}' gerado com sucesso!")
            if export_format == 'docx':
                return redirect('download_contract', contract_id=contract.id)
            return redirect('contracts_history')

        except Exception as e:
            messages.error(request, f"Falha ao gerar contrato: {str(e)}")

    return render(request, 'contracts/fill_template.html', {
        'template': template,
        'field_schema_json': json.dumps(schema),
        'structure_json': json.dumps(template.structure or {'blocks': []}),
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
        raise Http404("Arquivo de contrato não encontrado.")

    log_activity(
        'contract_download',
        f"Download do contrato '{contract.name}'.",
        user=request.user,
        entity_type='contract',
        entity_id=contract_id,
        request=request,
    )

    ext = os.path.splitext(contract.pdf_file.path)[1].lower()
    content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if ext == '.docx' else 'application/pdf'
    response = FileResponse(open(contract.pdf_file.path, 'rb'), content_type=content_type)
    safe_filename = contract.name.replace(" ", "_") + ext
    response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
    return response
