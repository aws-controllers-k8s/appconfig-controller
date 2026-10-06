	if ko.Status.ID != nil {
		resourceARN := fmt.Sprintf(
			"arn:%s:appconfig:%s:%s:application/%s",
			rm.awsPartition,
			rm.awsRegion,
			rm.awsAccountID,
			*ko.Status.ID,
		)
		arn := ackv1alpha1.AWSResourceName(resourceARN)
		ko.Status.ACKResourceMetadata.ARN = &arn

		listTagsInput := &svcsdk.ListTagsForResourceInput{
			ResourceArn: &resourceARN,
		}
		listTagsResp, err := rm.sdkapi.ListTagsForResource(ctx, listTagsInput)
		rm.metrics.RecordAPICall("GET_TAGS", "ListTagsForResource", err)
		if err != nil {
			return nil, err
		}
		ko.Spec.Tags = aws.StringMap(listTagsResp.Tags)
	}
