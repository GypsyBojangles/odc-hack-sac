def create_level3(dc, query):
    fcp = dc.load(product='ls_usgs_fcp_fiji', output_crs=output_crs, measurements= ['PV_PC_50', 'NPV_PC_50', 'BS_PC_50'], time=time, **query)
    
    if fcp:
        fcp = masking.mask_invalid_data(fcp).squeeze()
    else:
        return None, None
    
    wofs = dc.load(product='ls_usgs_wofs_fiji', output_crs=output_crs, measurements= ['count_clear'], time=time, **query)
    
    if wofs:
        wofs = masking.mask_invalid_data(wofs).squeeze()
    else:
        return None, None
    
    veg = ((fcp.PV_PC_50 >= 55) | (fcp.NPV_PC_50 >= 55)).where(fcp.PV_PC_50.notnull())
    vegetat_veg_cat_ds = veg.to_dataset(name="vegetat_veg_cat")
    
    # Load data from datacube
    s1 = dc.load(product="s1_gamma0_scene", output_crs=output_crs, time=time, **query)
    if s1:
        s1 = masking.mask_invalid_data(s1)
    else:
        return None, None

    s1 = (10**(s1/10))

    water = ((s1.vv <= 0.07) & (s1.vh <= 0.01))
    aquatic_wat_cat_ds = ((water.sum(dim='time') / water.count(dim="time")) >.2).to_dataset(name="aquatic_wat_cat")

    dummy = xarray.DataArray(numpy.zeros(water[0,:,:].shape), coords=[water[0,:,:].y.data, water[0,:,:].x.data], dims=['y', 'x'] )
    cultman_agr_cat_ds = dummy.to_dataset(name="cultman_agr_cat")

    urban = ((s1.vv.median(dim='time') > .5) | (s1.vh.median(dim='time') > .1))
    artific_urb_cat_ds = urban.to_dataset(name="artific_urb_cat")

    artwatr_wat_cat_ds = dummy.to_dataset(name="artwatr_wat_cat")
 
    variables_xarray_list = []
    variables_xarray_list.append(artwatr_wat_cat_ds)
    variables_xarray_list.append(aquatic_wat_cat_ds)
    variables_xarray_list.append(vegetat_veg_cat_ds)
    variables_xarray_list.append(cultman_agr_cat_ds)
    variables_xarray_list.append(artific_urb_cat_ds)

    classification_data = xarray.merge(variables_xarray_list)

    # Apply Level 3 classification using separate function. Works through in three stages
    level1, level2, level3 = lccs_l3.classify_lccs_level3(classification_data)
    level3_clean = numpy.where(wofs.count_clear > 0,level3, -1)

    return level3_clean, fcp
