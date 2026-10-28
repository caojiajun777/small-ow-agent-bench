def prefix_sums(nums, start=0):
    total = start
    for index in range(len(nums)):
        total += nums[index]
        nums[index] = total
    return nums

