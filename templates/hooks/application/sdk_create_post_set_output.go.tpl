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
	}
