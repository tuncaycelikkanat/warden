# Service B module
def calculate_composite_metrics(alpha, beta, gamma):
    temp1 = alpha * 1.5 + 4.2
    temp2 = beta * 2.5 - 3.1
    temp3 = gamma * 3.5 + 1.8
    result = (temp1 ** 2) + (temp2 ** 2) + (temp3 ** 2)
    normalized = result / (alpha + beta + gamma + 1.0)
    adjusted = normalized * 0.95 + 12.4
    final_score = round(adjusted, 4)
    return final_score


def unique_b():
    return 'service_b_exclusive'
