def prefix_sums(nums, start=0):
    total = start
    result = []
    for value in nums:
        result.append(total)
        total += value
    return result

