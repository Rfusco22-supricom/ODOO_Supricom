#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script rápido para probar las validaciones de RUC sin cargar Odoo"""

import re

def validate_ruc(ruc, ruc_type='natural'):
    """
    Valida el formato del RUC panameño
    """
    if not ruc:
        return True, "OK"
    
    ruc = ruc.strip().upper()
    
    # Extraer provincia, tomo y asiento
    parts = ruc.split('-')
    if len(parts) != 3:
        return False, "Debe tener 3 partes separadas por guiones"
    
    provincia, tomo, asiento = parts
    
    # Detectar si es persona natural o jurídica por el formato del tomo
    has_type_digit = tomo in ['2', '3'] or (len(tomo) >= 2 and tomo[0] in ['2', '3'] and tomo[1:].isdigit())
    
    # Validar según el tipo de RUC
    if ruc_type == 'natural':
        # Personas Naturales - Nuevos formatos
        pattern_new = re.compile(r'^(0?[1-9]|1[0-3])-(AV|PI|NT|PE|E|N)-\d{1,6}$')
        if pattern_new.match(ruc):
            # Validar provincia (1-13)
            try:
                prov_num = int(provincia)
                if prov_num < 1 or prov_num > 13:
                    return False, f"Provincia inválida: {prov_num} (debe ser 1-13)"
            except:
                pass
            return True, "Formato nuevo válido"
        
        # Formato antiguo (solo si NO tiene dígito de tipo 2 o 3)
        if not has_type_digit:
            pattern_old = re.compile(r'^(0?[1-9]|1[0-3])-\d{1,4}-\d{1,6}$')
            if pattern_old.match(ruc):
                # Validar provincia
                try:
                    prov_num = int(provincia)
                    if prov_num < 1 or prov_num > 13:
                        return False, f"Provincia inválida: {prov_num} (debe ser 1-13)"
                except:
                    return False, "Provincia debe ser numérica"
                return True, "Formato antiguo válido"
        
        return False, f"Formato de persona natural inválido. Esperado: PP-TIPO-NNNNNN o PP-NNNN-NNNNNN"
    
    elif ruc_type == 'juridica':
        # Personas Jurídicas - Formato con dígito de tipo
        pattern_new = re.compile(r'^\d{4,6}-(2|3)-\d{4,6}$')
        if pattern_new.match(ruc):
            # Validar longitudes
            if len(provincia) < 4 or len(provincia) > 6:
                return False, f"Primera parte debe tener 4-6 dígitos, tiene {len(provincia)}"
            if len(asiento) < 4 or len(asiento) > 6:
                return False, f"Tercera parte debe tener 4-6 dígitos, tiene {len(asiento)}"
            return True, "Formato jurídica válido"
        
        return False, f"Formato de persona jurídica inválido. Esperado: NNNNNN-2-NNNNNN o NNNNNN-3-NNNNNN"
    
    return False, "Tipo de RUC desconocido"


def run_tests():
    """Ejecuta todos los tests de validación"""
    
    test_cases = {
        'Personas Naturales - Nuevos Formatos': [
            # Panameños por nacimiento
            ('8-123-4567', 'natural', True),
            ('08-123-4567', 'natural', True),
            ('13-PI-12345', 'natural', True),
            ('1-AV-1', 'natural', True),
            
            # Panameños nacidos en el extranjero
            ('8-NT-12345', 'natural', True),
            ('1-NT-1', 'natural', True),
            
            # Panameños naturalizados
            ('8-N-12345', 'natural', True),
            
            # Extranjeros
            ('8-PE-12345', 'natural', True),
            ('8-E-12345', 'natural', True),
            
            # Formato antiguo válido
            ('8-123-456', 'natural', True),
            ('1-1-1', 'natural', True),
            ('13-9999-999999', 'natural', True),
        ],
        'Personas Naturales - Formatos Inválidos': [
            # Provincia inválida
            ('0-123-456', 'natural', False),
            ('14-123-456', 'natural', False),
            ('15-PI-12345', 'natural', False),
            
            # Tipo inválido
            ('8-XX-12345', 'natural', False),
            ('8-123-', 'natural', False),
            
            # Sin guiones
            ('8123456', 'natural', False),
        ],
        'Personas Jurídicas - Válidos': [
            # Tipo 2 (Sociedades Comerciales)
            ('155777-2-2019', 'juridica', True),
            ('1234-2-123456', 'juridica', True),
            ('123456-2-1234', 'juridica', True),
            
            # Tipo 3 (Instituciones No Comerciales)
            ('98765-3-54321', 'juridica', True),
            ('1234-3-123456', 'juridica', True),
        ],
        'Personas Jurídicas - Inválidos': [
            # Longitud incorrecta
            ('123-2-2019', 'juridica', False),  # Primera parte muy corta
            ('1234567-2-2019', 'juridica', False),  # Primera parte muy larga
            ('1234-2-123', 'juridica', False),  # Tercera parte muy corta
            ('1234-2-1234567', 'juridica', False),  # Tercera parte muy larga
            
            # Dígitos incorrectos (< 4 dígitos en primera o tercera parte)
            ('123-2-2019', 'juridica', False),
            ('1234-2-123', 'juridica', False),
            
            # Tipo inválido
            ('1234-5-123456', 'juridica', False),
            
            # 10 dígitos primera parte - debería fallar
            ('1234567890-2-2019', 'juridica', False),
            
            # 9 dígitos primera parte - debería fallar
            ('123456789-3-2020', 'juridica', False),
        ],
    }
    
    total = 0
    passed = 0
    failed = 0
    
    for category, cases in test_cases.items():
        print(f"\n{'='*60}")
        print(f"{category}")
        print(f"{'='*60}")
        
        for ruc, ruc_type, should_pass in cases:
            total += 1
            is_valid, message = validate_ruc(ruc, ruc_type)
            
            if is_valid == should_pass:
                passed += 1
                status = "✓ PASS"
            else:
                failed += 1
                status = "✗ FAIL"
            
            expected = "VÁLIDO" if should_pass else "INVÁLIDO"
            result = "VÁLIDO" if is_valid else "INVÁLIDO"
            
            print(f"{status}: {ruc:20s} (tipo: {ruc_type:8s}) - Esperado: {expected:8s}, Obtenido: {result:8s}")
            if is_valid != should_pass:
                print(f"       → {message}")
    
    print(f"\n{'='*60}")
    print(f"RESUMEN")
    print(f"{'='*60}")
    print(f"Total:   {total}")
    print(f"Pasados: {passed} ({100*passed/total:.1f}%)")
    print(f"Fallidos: {failed} ({100*failed/total:.1f}%)")
    
    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
