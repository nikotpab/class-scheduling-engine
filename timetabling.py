import pulp

docentes = ['Prof_A', 'Prof_B']

cursos = ['Calculo', 'Programacion']

aulas = ['Aula_101', 'Lab_Sistemas']

dias = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']

franjas = ['07:00-09:00', '09:00-11:00', '14:00-16:00', '18:00-20:00'] 


sesiones_requeridas = {'Calculo': 2, 'Programacion': 2}



disponibilidad = {
    ('Prof_A', '18:00-20:00'): 1,
    ('Prof_A', '07:00-09:00'): 0,
    ('Prof_A', '09:00-11:00'): 0,
    ('Prof_A', '14:00-16:00'): 0,
    ('Prof_B', '07:00-09:00'): 1,
    ('Prof_B', '09:00-11:00'): 1,
    ('Prof_B', '14:00-16:00'): 0,
    ('Prof_B', '18:00-20:00'): 0,
}


prob = pulp.LpProblem("Generacion_Horarios_Universidad", pulp.LpMinimize)



X = {}

for d in docentes:
    
    for c in cursos:
        
        for a in aulas:
            
            for dia in dias:
                
                for f in franjas:
                    
                    
                    X[(d, c, a, dia, f)] = pulp.LpVariable(f"X_{d}_{c}_{a}_{dia}_{f}", cat='Binary')




prob += 0, "Funcion_Objetivo_Simulada"


for c in cursos:
    
    
    prob += pulp.lpSum([X[(d, c, a, dia, f)] for d in docentes for a in aulas for dia in dias for f in franjas]) == sesiones_requeridas[c]


for d in docentes:
    for dia in dias:
        for f in franjas:
            
            prob += pulp.lpSum([X[(d, c, a, dia, f)] for c in cursos for a in aulas]) <= 1


for a in aulas:
    for dia in dias:
        for f in franjas:
            
            prob += pulp.lpSum([X[(d, c, a, dia, f)] for d in docentes for c in cursos]) <= 1


for d in docentes:
    for dia in dias:
        for f in franjas:
            
            disp = disponibilidad.get((d, f), 1)
            
            if disp == 0:
                prob += pulp.lpSum([X[(d, c, a, dia, f)] for c in cursos for a in aulas]) == 0



prob.solve()


print("Estado del modelo:", pulp.LpStatus[prob.status])
print("-" * 30)


for var in X.values():
    
    if var.varValue == 1.0:
        
        print(f"Clase programada: {var.name}")