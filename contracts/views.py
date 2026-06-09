import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse
from django.conf import settings
from django.core.files.base import ContentFile

from .models import ContractTemplate, GeneratedContract
from .parser import extract_placeholders_from_pdf
from .generator import generate_contract_pdf

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
            
        # Create template instance first
        template = ContractTemplate.objects.create(
            user=request.user,
            name=name,
            pdf_file=pdf_file
        )
        
        # Parse fields from the saved PDF file
        pdf_path = template.pdf_file.path
        detected = extract_placeholders_from_pdf(pdf_path)
        
        template.detected_fields = detected
        template.save()
        
        messages.success(request, f"Template '{name}' cadastrado! {len(detected)} campos dinâmicos identificados.")
        return redirect('fill_template', template_id=template.id)
        
    return render(request, 'contracts/templates_list.html', {
        'templates': templates,
        'current_page': 'contracts'
    })


@login_required
def delete_template_view(request, template_id):
    template = get_object_or_404(ContractTemplate, id=template_id, user=request.user)
    name = template.name
    # Delete actual file on disk
    if template.pdf_file:
        if os.path.exists(template.pdf_file.path):
            os.remove(template.pdf_file.path)
            
    template.delete()
    messages.success(request, f"Template '{name}' removido com sucesso.")
    return redirect('template_list')


@login_required
def fill_template_view(request, template_id):
    template = get_object_or_404(ContractTemplate, id=template_id, user=request.user)
    
    if request.method == 'POST':
        contract_name = request.POST.get('contract_name', '').strip() or f"Contrato - {template.name}"
        
        # Build dictionary of replacements from form fields
        filled_data = {}
        for field in template.detected_fields:
            val = request.POST.get(f"field_{field}", "").strip()
            filled_data[field] = val
            
        # Create directories inside media folder if not exist
        gen_dir = os.path.join(settings.MEDIA_ROOT, 'generated_contracts')
        os.makedirs(gen_dir, exist_ok=True)
        
        # Output filepath
        safe_name = "".join(x for x in contract_name if x.isalnum() or x in " -_").strip()
        filename = f"{request.user.id}_{template.id}_{safe_name}.pdf"
        output_filepath = os.path.join(gen_dir, filename)
        
        try:
            # Generate the document
            generate_contract_pdf(
                template_path=template.pdf_file.path,
                filled_data=filled_data,
                output_path=output_filepath,
                contract_title=contract_name
            )
            
            # Save generated file to db
            # We want to associate the file path relative to MEDIA_ROOT
            rel_file_path = f"generated_contracts/{filename}"
            
            contract = GeneratedContract.objects.create(
                user=request.user,
                template=template,
                name=contract_name,
                filled_data=filled_data,
                pdf_file=rel_file_path
            )
            
            messages.success(request, f"Contrato '{contract_name}' gerado com sucesso!")
            return redirect('contracts_history')
            
        except Exception as e:
            messages.error(request, f"Falha ao gerar contrato: {str(e)}")
            
    return render(request, 'contracts/fill_template.html', {
        'template': template,
        'current_page': 'contracts'
    })


@login_required
def contracts_history_view(request):
    contracts = GeneratedContract.objects.filter(user=request.user)
    return render(request, 'contracts/history.html', {
        'contracts': contracts,
        'current_page': 'contracts'
    })


@login_required
def delete_contract_view(request, contract_id):
    contract = get_object_or_404(GeneratedContract, id=contract_id, user=request.user)
    name = contract.name
    # Delete file from disk
    if contract.pdf_file:
        if os.path.exists(contract.pdf_file.path):
            os.remove(contract.pdf_file.path)
            
    contract.delete()
    messages.success(request, f"Documento '{name}' removido do histórico.")
    return redirect('contracts_history')


@login_required
def download_contract_view(request, contract_id):
    contract = get_object_or_404(GeneratedContract, id=contract_id, user=request.user)
    
    if not contract.pdf_file or not os.path.exists(contract.pdf_file.path):
        raise Http404("Arquivo de contrato não encontrado.")
        
    response = FileResponse(open(contract.pdf_file.path, 'rb'), content_type='application/pdf')
    # Set headers to download file with formatted client name
    safe_filename = contract.name.replace(" ", "_") + ".pdf"
    response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
    return response
